from nonebot import on_command
from nonebot import permission as SUPERUSER
from nonebot.adapters.cqhttp import Bot, Event, permission, MessageSegment
from nonebot.rule import to_me

from .RSS import rss_class
from .util import text2img

RssShowAll = on_command('showall', aliases={'selectall', '所有订阅'}, rule=to_me(), priority=5,
                        permission=SUPERUSER.SUPERUSER | permission.GROUP_ADMIN | permission.GROUP_OWNER | permission.PRIVATE_FRIEND)


@RssShowAll.handle()
async def handle_first_receive(bot: Bot, event: Event, state: dict):
    rss = rss_class.rss('', '', '-1', '-1')
    rss_list = rss.readRss()
    if rss_list:
        if len(rss_list) == 1:
            await RssShowAll.send(rss_list[0].toString())
        else:
            flag = 0
            info = ''
            for rss_tmp in rss_list:
                if flag % 5 == 0 and flag != 0:
                    await RssShowAll.send(str(info[:-2]))
                    info = ''
                info += 'Name：{}\nURL：{}\n\n'.format(rss_tmp.name, rss_tmp.url)
                flag += 1
            await RssShowAll.send(MessageSegment.image(text2img(info))+'共 {} 条可用订阅'.format(flag))

    else:
        await RssShowAll.send('当前没有任何订阅！')
        return
