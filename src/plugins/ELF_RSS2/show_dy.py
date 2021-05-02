from nonebot import on_command
from nonebot import permission as SUPERUSER
from nonebot.adapters.cqhttp import Bot, Event, permission, unescape
from nonebot.rule import to_me
from nonebot.permission import _superuser

from .RSS import rss_class

RssShow = on_command('show', aliases={'查看订阅'}, rule=to_me(
), priority=5, permission=SUPERUSER.SUPERUSER | permission.GROUP_ADMIN | permission.GROUP_OWNER | permission.PRIVATE_FRIEND)

# 不带订阅名称默认展示当前群组或账号的订阅
# 带订阅名称就显示该订阅的

@RssShow.handle()
async def handle_first_receive(bot: Bot, event: Event, state: dict):
    args = str(event.message).strip()  # 首次发送命令时跟随的参数，例：/天气 上海，则args为上海
    if args:
        rss_name = unescape(args)  # 如果用户发送了参数则直接赋值
    else:
        rss_name = None
    user_id = event.user_id
    group_id = None
    if event.message_type == 'group':
        group_id = event.group_id

    rss = rss_class.rss('', '', '-1', '-1')

    if rss_name:
        rss = rss.findName(str(rss_name))
        if not rss:
            await RssShow.send('❌ 订阅 {} 不存在！'.format(rss_name))
            return
        if group_id:
            if not str(group_id) in rss.group_id:
                await RssShow.send('❌ 本群未订阅 {}。本订阅详情如下'.format(rss_name))
                rss.group_id = ['*']
            else:
                rss.group_id = [str(group_id), '*']
            rss.user_id = ['*']
        elif user_id and not await _superuser(bot, event):
            if not str(user_id) in rss.user_id:
                await RssShow.send('❌ 本用户未订阅 {}。本订阅详情如下'.format(rss_name))
                rss.user_id = ['*']
            else:
                rss.user_id = [str(user_id), '*']
            rss.group_id = ['*']
        elif user_id and await _superuser(bot, event):
            if not str(user_id) in rss.user_id:
                await RssShow.send('❌ 本用户未订阅 {}。本订阅详情如下'.format(rss_name))
                
        await RssShow.send(str(rss))
        return

    if group_id:
        rss_list = rss.findGroup(group=str(group_id))
        if not rss_list:
            await RssShow.send('❌ 当前群组没有任何订阅！')
            return
    else:
        rss_list = rss.findUser(user=str(user_id))
        if not rss_list:
            await RssShow.send('❌ 当前用户没有任何订阅！')
            return
    if rss_list:
        if len(rss_list) == 1:
            if group_id:
                rss_list[0].group_id = [str(group_id), '*']
                rss_list[0].user_id = ['*']
            elif user_id and not await _superuser(bot, event):
                rss_list[0].group_id = ['*']
                rss_list[0].user_id = [str(user_id), '*']
            await RssShow.send(str(rss_list[0]))
        else:
            flag = 0
            info = ''
            for rss_tmp in rss_list:
                if flag % 5 == 0 and flag != 0:
                    await RssShow.send(str(info))
                    info = ''
                info += 'Name：{}\nURL：{}\n\n'.format(rss_tmp.name, rss_tmp.url)
                flag += 1
            await RssShow.send(info+'共 {} 条订阅'.format(flag))

    else:
        await RssShow.send('❌ 当前没有任何订阅！')
        return

# @RssShow.got("RssShow", prompt="")
# async def handle_RssAdd(bot: Bot, event: Event, state: dict):
#     rss_name = state["RssShow"]
