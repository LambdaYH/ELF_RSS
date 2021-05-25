from nonebot import on_command
from nonebot import permission as su
from nonebot.adapters.cqhttp import Bot, Event, GroupMessageEvent, permission
from nonebot.rule import to_me

from .RSS import rss_class
from .util import text2img

RSS_SHOW_ALL = on_command(
    "showall",
    aliases={"selectall", "所有订阅"},
    rule=to_me(),
    priority=5,
    permission=su.SUPERUSER
    | permission.GROUP_ADMIN
    | permission.GROUP_OWNER
    | permission.PRIVATE_FRIEND,
)


@RSS_SHOW_ALL.handle()
async def handle_first_receive(bot: Bot, event: Event, state: dict):
    rss = rss_class.Rss("", "", "-1", "-1")
    rss_list = rss.read_rss()
    if rss_list:
        if len(rss_list) == 1:
            await RSS_SHOW_ALL.send(str(rss_list[0]))
        else:
            flag = 0
            info = ""
            for rss_tmp in rss_list:
                if flag % 5 == 0 and flag != 0:
                    await RSS_SHOW_ALL.send(str(info[:-2]))
                    info = ""
                info += f"Name：{rss_tmp.name}\nURL：{rss_tmp.url}\n\n"
                flag += 1
            await RSS_SHOW_ALL.send(f"{info}共 {flag} 条可用订阅，发送[show 订阅名]可查看订阅详情")

    else:
        await RSS_SHOW_ALL.send("当前没有任何订阅！")
