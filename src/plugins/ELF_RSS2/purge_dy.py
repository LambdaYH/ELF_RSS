import os
from pathlib import Path

from nonebot import on_command
from nonebot import permission as SUPERUSER
from nonebot import require
from nonebot.adapters.cqhttp import Bot, Event, unescape
from nonebot.rule import to_me

from .RSS import rss_class
from .RSS import my_trigger as tr

scheduler = require("nonebot_plugin_apscheduler").scheduler
# 存储目录
file_path = str(str(Path.cwd()) + os.sep + "data" + os.sep)

RSS_PURGE = on_command("purgedy", rule=to_me(), priority=5, permission=SUPERUSER.SUPERUSER)


@RSS_PURGE.handle()
async def handle_first_receive(bot: Bot, event: Event, state: dict):
    args = str(event.message).strip()  # 首次发送命令时跟随的参数，例：/天气 上海，则args为上海
    if args:
        state["RSS_PURGE"] = unescape(args)  # 如果用户发送了参数则直接赋值


@RSS_PURGE.got("RSS_PURGE", prompt="输入要删除的订阅名")
async def handle_RssAdd(bot: Bot, event: Event, state: dict):
    rss_name = unescape(state["RSS_PURGE"])
    rss = rss_class.Rss('', '', '-1', '-1')
    if rss.find_name(name=rss_name):
        rss = rss.find_name(name=rss_name)
    else:
        await RSS_PURGE.send('❌ 删除失败！不存在该订阅！')
        return
    rss.delete_rss(rss)
    await tr.delete_job(rss)
    await RSS_PURGE.send('👏 订阅 {} 删除成功！'.format(rss.name))
