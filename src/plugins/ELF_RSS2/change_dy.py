import re

from nonebot import on_command
from nonebot import permission as SUPERUSER
from nonebot import require
from nonebot.adapters.cqhttp import Bot, Event, permission, unescape
from nonebot.log import logger
from nonebot.rule import to_me

from .RSS import rss_class
from .RSS import my_trigger as TR

scheduler = require("nonebot_plugin_apscheduler").scheduler

# 存储目录
# file_path = './data/'

RssChange = on_command('change', aliases={'修改订阅', 'moddy'}, rule=to_me(), priority=5,
                       permission=SUPERUSER.SUPERUSER | permission.GROUP_ADMIN | permission.GROUP_OWNER | permission.PRIVATE_FRIEND)


@RssChange.handle()
async def handle_first_receive(bot: Bot, event: Event, state: dict):
    args = str(event.message).strip()
    if args:
        state["RssChange"] = unescape(args)  # 如果用户发送了参数则直接赋值
    else:
        await RssChange.send('请输入要修改的订阅'
                             '\n订阅名 属性=,值'
                             '\n如:'
                             '\ntest qq=,123,234 qun=-1'
                             '\n对应参数:'
                             '\n订阅链接-url QQ-qq 群-qun 更新频率-time'
                             '\n代理-proxy 翻译-tl 仅title-ot，仅图片-op'
                             '\n下载种子-downopen 白名单关键词-wkey 黑名单关键词-bkey 种子上传到群-upgroup'
                             '\n去重模式-mode'
                             '\n注：'
                             '\nproxy、tl、ot、op、downopen、upgroup 值为 1/0'
                             '\n去重模式分为按链接(link)、标题(title)、图片(image)判断'
                             '\n其中 image 模式,出于性能考虑以及避免误伤情况发生,生效对象限定为只带 1 张图片的消息,'
                             '\n并且不建议用在一条消息可能带多张图片的 feed 源上,否则会出现这种误伤情况:'
                             '\n新的带多图的消息里含有上一条只带 1 张图片的消息中的图片,因此被过滤掉'
                             '\n白名单关键词支持正则表达式，匹配时推送消息及下载，设为空(wkey=)时不生效'
                             '\n黑名单关键词同白名单一样，只是匹配时不推送，两者可以一起用'
                             '\nQQ、群号、去重模式前加英文逗号表示追加,-1设为空'
                             '\n各个属性空格分割'
                             '\n详细：https://oy.mk/ckL'.strip())


# 处理带多个值的订阅参数
def handle_property(value: str, property_list: list) -> list:
    # 清空
    if value == '-1':
        return []
    value_list = value.split(',')
    # 追加
    if value_list[0] == "":
        value_list.pop(0)
        return property_list + [i for i in value_list if i not in property_list]
    return value_list


attribute_dict = {'qq': 'user_id', 'qun': 'group_id', 'url': 'url', 'time': 'time',
                  'proxy': 'img_proxy', 'tl': 'translation', 'ot': 'only_title',
                  'op': 'only_pic', 'upgroup': 'is_open_upload_group',
                  'downopen': 'down_torrent', 'downkey': 'down_torrent_keyword',
                  'wkey': 'down_torrent_keyword', 'blackkey': 'black_keyword',
                  'bkey': 'black_keyword', 'mode': 'duplicate_filter_mode'}


# 处理要修改的订阅参数
def handle_change_list(rss: rss_class.rss, key_to_change: str, value_to_change: str, group_id: int):
    # 暂时禁止群管理员修改 QQ / 群号，如要取消订阅可以使用 deldy 命令
    if (key_to_change in ['qq', 'qun'] and not group_id) or key_to_change == 'mode':
        value_to_change = handle_property(value_to_change, getattr(rss, attribute_dict[key_to_change]))
    elif key_to_change == 'url':
        rss.delete_file()
    elif key_to_change == 'time':
        if not re.search(r'[_*/,-]', value_to_change):
            if int(float(value_to_change)) < 1:
                value_to_change = '1'
            else:
                value_to_change = str(int(float(value_to_change)))
    elif key_to_change in ['proxy', 'tl', 'ot', 'op', 'upgroup', 'downopen']:
        value_to_change = bool(int(value_to_change))
    elif key_to_change in ['downkey', 'wkey', 'blackkey', 'bkey'] and len(value_to_change.strip()) == 0:
        value_to_change = None
    setattr(rss, attribute_dict.get(key_to_change), value_to_change)


@RssChange.got("RssChange", prompt='')
async def handle_RssAdd(bot: Bot, event: Event, state: dict):
    change_info = unescape(state["RssChange"])
    group_id = None
    if event.message_type == 'group':
        group_id = event.group_id
    change_list = change_info.split(' ')

    try:
        name = change_list[0]
        change_list.remove(name)
    except Exception:
        await RssChange.send('❌ 订阅名称参数错误！')
        return

    rss = rss_class.rss(name, '', '-1', '-1')
    if not rss.findName(name=name):
        await RssChange.send(f'❌ 订阅 {name} 不存在！')
        return

    rss = rss.findName(name=name)
    if group_id and str(group_id) not in rss.group_id:
        await RssChange.send(f'❌ 修改失败，当前群组无权操作订阅：{rss.name}')
        return

    try:
        for change_dict in change_list:
            key_to_change, value_to_change = change_dict.split('=', 1)
            if key_to_change in attribute_dict.keys():
                handle_change_list(rss, key_to_change, value_to_change, group_id)
            else:
                await RssChange.send(f'❌ 参数错误或无权修改！\n{change_dict}')
                return
        # 参数解析完毕，写入
        rss.writeRss()
        # 加入定时任务
        await TR.addJob(rss)
        if group_id:
            # 隐私考虑，群组下不展示除当前群组外的群号和QQ
            # 奇怪的逻辑，群管理能修改订阅消息，这对其他订阅者不公平。
            rss.group_id = [str(group_id), '*']
            rss.user_id = ['*']
        await RssChange.send(f'👏 修改成功\n{rss}')
        logger.info(f'👏 修改成功\n{rss}')

    except Exception as e:
        await RssChange.send(f'❌ 参数解析出现错误！\nE: {e}')
        logger.error(f'❌ 参数解析出现错误！\nE: {e}')
        raise
