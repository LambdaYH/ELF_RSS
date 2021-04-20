# -*- coding: UTF-8 -*-

import asyncio
import base64
import codecs
import difflib
import json
import os.path
import random
import re
import time
import unicodedata
import uuid
from io import BytesIO
from pathlib import Path

import aiofiles
import emoji
import feedparser
import httpx
import nonebot
from google_trans_new import google_translator
from nonebot.log import logger
from PIL import Image
from pyquery import PyQuery as pq
from retrying import retry

from ..config import config
from . import rss_class, translation_baidu
# 存储目录
from .qbittorrent_download import start_down

file_path = str(str(Path.cwd()) + os.sep + 'data' + os.sep)


# 代理
def get_Proxy(open_proxy: bool) -> dict:
    if not open_proxy:
        return {}
    proxy = config.rss_proxy
    return httpx.Proxy(
        url="http://" + proxy,
        # May be "TUNNEL_ONLY" or "FORWARD_ONLY". Defaults to "DEFAULT".
        mode="TUNNEL_ONLY"
    ) if proxy else {}


status_code = [200, 301, 302]
# 去掉烦人的 returning true from eof_received() has no effect when using ssl httpx 警告
asyncio.log.logger.setLevel(40)
headers = {
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'max-age=0',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36',
    'Connection': 'keep-alive',
    'Content-Type': 'application/xml; charset=utf-8'
}


# 入口
async def start(rss: rss_class.rss) -> None:
    # 网络加载 新RSS
    # 读取 旧RSS 记录
    # 检查更新
    # 对更新的 RSS 记录列表进行处理，当发送成功后才写入，成功一条写一条

    try:
        new_rss = await get_rss(rss)
    except:
        return
    new_rss_list = new_rss.entries
    try:
        old_rss_list = readRss(rss.name)['entries']
    except BaseException as e:
        writeRss(name=rss.name, new_rss=new_rss, new_item=None)
        logger.info('{} 订阅第一次抓取成功！'.format(rss.name))
        return

    change_rss_list = checkUpdate(new=new_rss_list, old=old_rss_list)
    if len(change_rss_list) <= 0:
        # 没有更新，返回
        logger.info('{} 没有新信息'.format(rss.name))
        return
    for item in change_rss_list:
        # 检查是否包含屏蔽词
        if config.showblockword == False:
            match = re.findall("|".join(config.blockword), item['summary'])
            if match:
                logger.info('内含屏蔽词，已经取消推送该消息')
                write_item(rss=rss, new_rss=new_rss, new_item=item)
                continue
        # 检查是否匹配关键词 使用 down_torrent_keyword 字段
        if rss.down_torrent_keyword:
            if not re.search(rss.down_torrent_keyword, item['summary']):
                write_item(rss=rss, new_rss=new_rss, new_item=item)
                continue
        # 检查是否匹配黑名单关键词 使用 black_keyword 字段
        if rss.black_keyword:
            if re.search(rss.black_keyword, item['summary']):
                write_item(rss=rss, new_rss=new_rss, new_item=item)
                continue
        # 检查是否只推送有图片的消息
        if rss.only_pic and not re.search('<img.+?>', item['summary']):
            logger.info('已开启仅图片，该消息没有图片，将跳过')
            write_item(rss=rss, new_rss=new_rss, new_item=item)
            continue

        item_msg = f"{new_rss.feed.title}\'s Feed\n====================\n"
        # 处理标题
        if not rss.only_title:
            # 先判断与正文相识度，避免标题正文一样，或者是标题为正文前N字等情况

            # 处理item['summary']只有图片的情况
            text = re.sub('<video.+?><\/video>|<img.+?>', '', item['summary'])
            text = re.sub('<br>', '', text)
            Similarity = difflib.SequenceMatcher(None, text, item['title'])
            if Similarity.quick_ratio() <= 0.1:  # 标题正文相似度
                item_msg += await handle_title(title=item['title'])

            # 处理正文
            item_msg += await handle_summary(summary=item['summary'], rss=rss)
        else:
            item_msg += await handle_title(title=item['title'])

        # 处理来源
        item_msg += await handle_source(source=item['link'])

        # 处理时间
        try:
            item_msg += await handle_date(date=item['published_parsed'])
        except:
            item_msg += await handle_date()

        # 处理种子
        try:
            hash_list = await handle_down_torrent(rss=rss, item=item)
            if hash_list and len(hash_list) > 0 and hash_list[0] != None:
                item_msg += '\n磁力：\n'
                for h in hash_list:
                    item_msg += f'magnet:?xt=urn:btih:{h}\n'
                item_msg = item_msg[:-1]
        except Exception as e:
            logger.error('下载种子时出错：{}'.format(e))
        # 发送消息并写入文件
        if await sendMsg(rss=rss, msg=item_msg):
            write_item(rss=rss, new_rss=new_rss, new_item=item)


# 写入单条消息
def write_item(rss: rss_class.rss, new_rss: list, new_item: str):
    tmp = []
    tmp.append(new_item)
    writeRss(name=rss.name, new_rss=new_rss, new_item=tmp)


# 下载种子判断


async def handle_down_torrent(rss: rss_class, item: dict) -> list:
    if not rss.is_open_upload_group:
        rss.group_id = []
    if config.is_open_auto_down_torrent and rss.down_torrent:
        if rss.down_torrent_keyword:
            if re.search(rss.down_torrent_keyword, item['summary']):
                return await down_torrent(rss=rss, item=item, proxy=get_Proxy(rss.img_proxy))
        else:
            return await down_torrent(rss=rss, item=item, proxy=get_Proxy(rss.img_proxy))


# 创建下载种子任务


async def down_torrent(rss: rss_class, item: dict, proxy=None) -> list:
    hash_list = []
    for tmp in item['links']:
        if tmp['type'] == 'application/x-bittorrent' or tmp['href'].find('.torrent') > 0:
            hash_list.append(await start_down(url=tmp['href'], group_ids=rss.group_id,
                                              name='{}'.format(rss.name),
                                              path=file_path + os.sep + 'torrent' + os.sep, proxy=proxy))
    return hash_list


# 获取 RSS 并解析为 json ，失败重试


@retry(stop_max_attempt_number=5, stop_max_delay=30 * 1000)
async def get_rss(rss: rss_class.rss) -> dict:
    # 判断是否使用cookies
    if rss.cookies:
        cookies = rss.cookies
    else:
        cookies = None

    # 获取 xml
    async with httpx.AsyncClient(proxies=get_Proxy(open_proxy=rss.img_proxy), cookies=cookies,
                                 headers=headers) as client:
        try:
            r = await client.get(rss.geturl())
            # 解析为 JSON
            d = feedparser.parse(r.content)
        except BaseException as e:
            # logger.error("抓取订阅 {} 的 RSS 失败，将重试 ！ E：{}".format(rss.name, e))
            if not re.match(u'[hH][tT]{2}[pP][sS]{0,}://', rss.url, flags=0) and config.rsshub_backup:
                logger.error('RSSHub :' + config.rsshub +
                             ' 访问失败 ！使用备用RSSHub 地址！')
                for rsshub_url in list(config.rsshub_backup):
                    async with httpx.AsyncClient(proxies=get_Proxy(open_proxy=rss.img_proxy)) as client:
                        try:
                            r = await client.get(rss.geturl(rsshub=rsshub_url))
                        except Exception as e:
                            logger.error(
                                'RSSHub :' + rss.geturl(rsshub=rsshub_url) + ' 访问失败 ！使用备用 RSSHub 地址！')
                            continue
                        if r.status_code in status_code:
                            d = feedparser.parse(r.content)
                            if d.entries:
                                logger.info(rss.geturl(
                                    rsshub=rsshub_url) + ' 抓取成功！')
                                break
        try:
            if d.entries:
                pass
        except:
            if rss.cookies:
                cookies_str = '\n如果设置了 cookies 请检查 cookies 正确性'
            else:
                cookies_str = ''
            e_msg = rss.name + ' 抓取失败！已经重试 5 次！请检查订阅地址 {} {}\n如果是网络问题，请忽略该错误！'.format(rss.geturl(), cookies_str)
            logger.error(e_msg)
            raise Exception(e_msg)
        return d


# 处理标题
async def handle_title(title: str) -> str:
    return '标题：' + title + '\n'


# 处理正文，图片放后面
async def handle_summary(summary: str, rss: rss_class.rss) -> str:
    # 去掉换行
    # summary = re.sub('\n', '', summary)
    # 处理 summary 使其 HTML标签统一，方便处理
    try:
        summary_html = pq(summary)
    except:
        logger.info('{} 没有正文内容！', rss.name)
        return ''
    # 最终消息初始化
    res_msg = ''

    # 判断是否开启了 仅仅推送有图片的信息
    if not rss.only_pic:
        # 处理标签及翻译
        res_msg += await handle_html_tag(html=summary_html, translation=rss.translation)

    # 处理图片
    res_msg += await handle_img(html=summary_html, img_proxy=rss.img_proxy)

    return res_msg + '\n'


# 处理来源
async def handle_source(source: str) -> str:
    # 缩短 pixiv 链接
    str_link = re.sub('https://www.pixiv.net/artworks/',
                      'https://pixiv.net/i/', source)
    return '链接：' + str_link + '\n'


# 处理日期
async def handle_date(date=None) -> str:
    if date:
        rss_time = time.mktime(date)
        # 时差处理，待改进
        if rss_time + 28800.0 < time.time():
            rss_time += 28800.0
        return '日期：' + time.strftime("%m{}%d{} %H:%M:%S",
                                     time.localtime(rss_time)).format('月', '日')
    # 没有日期的情况，以当前时间
    else:
        return '日期：' + time.strftime("%m{}%d{} %H:%M:%S", time.localtime()).format('月', '日')


# 图片压缩
async def zipPic(content, file_type):
    # 打开一个jpg/png图像文件，注意是当前路径:
    im = Image.open(BytesIO(content))
    # 获得图像尺寸:
    width, height = im.size
    # 算出缩小比
    Proportion = int(len(content) / (float(config.zip_size) * 1024))
    logger.info('算出的缩小比:' + str(Proportion))
    if Proportion > 0:
        # 缩放
        im.thumbnail((width // Proportion, height // Proportion))
    width, height = im.size
    logger.info('Resize image to: %sx%s' % (width, height))
    # 和谐
    pim = im.load()
    points = [[0, 0], [width - 1, 0], [0, height - 1], [width - 1, height - 1]]
    try:
        for point in points:
            if file_type == 'png':
                im.putpixel((point[0], point[1]), random.randint(0, 255))
            elif file_type == 'jpg':
                pim[point[0], point[1]] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    except:
        logger.error('图片和谐失败！')
    return im


# 将图片转化为 base64
async def get_pic_base64(content, file_type) -> str:
    # im = Image.open(BytesIO(content))
    im = await zipPic(content, file_type)
    jpeg_image_buffer = BytesIO()
    im.save(jpeg_image_buffer, file_type)
    res = str(base64.b64encode(jpeg_image_buffer.getvalue()), encoding="utf-8")
    return res


# 去你的 pixiv.cat
async def fuck_pixiv(url: str) -> str:
    if url.find('pixiv.cat'):
        img_id = re.sub('https://pixiv.cat/', '', url)
        img_id = img_id[:-4]
        info_list = img_id.split('-')
        async with httpx.AsyncClient(proxies={}) as client:
            try:
                req_json = (await client.get('https://hibiapi.getloli.com/api/pixiv/illust?id=' + info_list[0])).json()
                if len(info_list) >= 2:
                    return req_json['illust']['meta_pages'][int(info_list[1]) - 1]['image_urls']['original']
                else:
                    return req_json['illust']['meta_single_page']['original_image_url']
            except Exception as e:
                logger.error('处理pixiv.cat链接时出现问题 ：{}'.format(e))
                return url
    else:
        return url


@retry(stop_max_attempt_number=5, stop_max_delay=30 * 1000)
async def dowimg(url: str, proxy: bool) -> str:
    try:
        async with httpx.AsyncClient(proxies=get_Proxy(open_proxy=proxy)) as client:
            if config.close_pixiv_cat:
                url = await fuck_pixiv(url=url)
            referer = re.findall('([hH][tT]{2}[pP][sS]{0,}://.*?)(?:/.*?)', url)[0]
            headers = {'referer': referer}
            pic = await client.get(url, headers=headers)
            # image/gif, image/png, image/jpeg, image/bmp, image/webp, image/x-icon, image/vnd.microsoft.icon
            if pic.headers['Content-Type'] == 'image/jpeg':
                file_type = 'jpeg'
            elif pic.headers['Content-Type'] == 'image/png':
                file_type = 'png'
            elif pic.headers['Content-Type'] == 'image/gif':
                file_type = 'gif'
            else:
                file_type = 'jpeg'
            return await get_pic_base64(pic.content, file_type)
    except BaseException as e:
        logger.error('图片下载失败,将重试 E:' + str(e))
        raise BaseException


# 处理图片、视频
async def handle_img(html: str, img_proxy: bool) -> str:
    img_str = ''
    # 处理图片
    doc_img = html('img')
    for img in doc_img.items():
        if img.attr("src"):
            img_base64 = await dowimg(img.attr("src"), img_proxy)
            if img_base64 != None or len(img_base64) > 0:
                img_str += '[CQ:image,file=base64://' + img_base64 + ']'
            else:
                img_str += '\n图片走丢啦: {} \n'.format(img.attr("src"))

    # 处理视频
    doc_video = html('video')
    if doc_video:
        img_str += '视频封面：'
        for video in doc_video.items():
            img_base64 = await dowimg(video.attr("poster"), img_proxy)
            if img_base64 != None or len(img_base64) > 0:
                img_str += '[CQ:image,file=base64://' + img_base64 + ']'
            else:
                img_str += '\n图片走丢啦: {} \n'.format(video.attr("poster"))

    # 解决 issue36
    img_list = re.findall(
        '(?:\[img])([hH][tT]{2}[pP][sS]{0,}://.*?)(?:\[/img])', str(html))
    for img_tmp in img_list:
        img_base64 = await dowimg(img_tmp, img_proxy)
        if img_base64 != None or len(img_base64) > 0:
            img_str += '[CQ:image,file=base64://' + img_base64 + ']'
        else:
            img_str += '\n图片走丢啦: {} \n'.format(img_tmp)

    return img_str


# HTML标签等处理
async def handle_html_tag(html, translation: bool) -> str:
    # issue36 处理md标签
    rss_str = re.sub(
        '\[img][hH][tT]{2}[pP][sS]{0,}://.*?\[/img]', '', str(html))
    rss_str = re.sub('(\[.*?=.*?])|(\[/.*?])', '', str(rss_str))

    # 处理一些 HTML 标签
    if config.blockquote == True:
        rss_str = re.sub('<blockquote>|</blockquote>', '', str(rss_str))
    else:
        rss_str = re.sub('<blockquote.*>', '', str(rss_str))
    rss_str = re.sub('<br/><br/>|<br><br>|<br>|<br/>', '\n', rss_str)
    rss_str = re.sub('<span>|<span.+?\">|</span>', '', rss_str)
    rss_str = re.sub('<pre.+?\">|</pre>', '', rss_str)
    rss_str = re.sub('<p>|<p.+?\">|</p>|<b>|<b.+?\">|</b>', '', rss_str)
    rss_str = re.sub('<div>|<div.+?\">|</div>', '', rss_str)
    rss_str = re.sub('<div>|<div.+?\">|</div>', '', rss_str)
    rss_str = re.sub('<iframe.+?\"/>', '', rss_str)
    rss_str = re.sub('<i.+?\">|<i>|</i>', '', rss_str)
    rss_str = re.sub('<code>|</code>|<ul>|</ul>', '', rss_str)
    # 解决 issue #3
    rss_str = re.sub('<dd.+?\">|<dd>|</dd>', '', rss_str)
    rss_str = re.sub('<dl.+?\">|<dl>|</dl>', '', rss_str)
    rss_str = re.sub('<dt.+?\">|<dt>|</dt>', '', rss_str)

    # 删除图片、视频标签
    rss_str = re.sub('<video.+?><\/video>|<img.+?>', '', rss_str)

    rss_str_tl = rss_str  # 翻译用副本
    # <a> 标签处理
    doc_a = html('a')
    for a in doc_a.items():
        if a.text():
            if str(a.text()) != a.attr("href"):
                rss_str = re.sub(re.escape(str(a)), str(
                    a.text()) + ':' + (a.attr("href")) + '\n', rss_str)
            else:
                rss_str = re.sub(re.escape(str(a)),
                                 (a.attr("href")) + '\n', rss_str)
            rss_str_tl = re.sub(re.escape(str(a)), '', rss_str_tl)

    # 删除未解析成功的 a 标签
    rss_str = re.sub('<a.+?\">|<a>|</a>', '', rss_str)
    rss_str_tl = re.sub('<a.+?\">|<a>|</a>', '', rss_str_tl)
    # 去掉换行
    rss_str = re.sub('\n\n|\n\n\n', '', rss_str)
    rss_str_tl = re.sub('\n\n|\n\n\n', '', rss_str_tl)

    if config.max_length > 0 and len(rss_str) > config.max_length:
        rss_str = rss_str[:config.max_length] + '...'
        rss_str_tl = rss_str_tl[:config.max_length] + '...'
    # 翻译
    if translation:
        return rss_str + await handle_translation(rss_str_tl=rss_str_tl)
    else:
        return rss_str


# 翻译
async def handle_translation(rss_str_tl: str) -> str:
    translator = google_translator()
    # rss_str_tl = re.sub(r'\n', ' ', rss_str_tl)
    try:
        text = emoji.demojize(rss_str_tl)
        text = re.sub(r':[A-Za-z_]*:', ' ', text)
        if config.usebaidu:
            rss_str_tl = re.sub(r'\n', '百度翻译 ', rss_str_tl)
            rss_str_tl = unicodedata.normalize('NFC', rss_str_tl)
            text = emoji.demojize(rss_str_tl)
            text = re.sub(r':[A-Za-z_]*:', ' ', text)
            text = '\n翻译(BaiduAPI)：\n' + \
                   str(translation_baidu.baidu_translate(re.escape(text)))
        else:
            text = '\n翻译：\n' + \
                   str(translator.translate(re.escape(text), lang_tgt='zh'))
        text = re.sub(r'\\', '', text)
        text = re.sub(r'百度翻译', '\n', text)
    except Exception as e:
        text = '\n翻译失败！' + str(e) + '\n'
    return text


# 检查更新
def checkUpdate(new, old) -> list:
    a = new
    b = old
    c = []
    for i in a:
        count = 0
        for j in b:
            try:
                if i['id'] == j['id']:
                    count = 1
            except:
                if i['link'] == j['link']:
                    count = 1
        if count == 0:
            c.insert(0, i)
    tmp = c.copy()
    for i in tmp:
        count = 0
        for j in b:
            # 当 item 不存在 id 时，使用 link
            try:
                if i['id'] == j['id']:
                    count = 1
            except:
                if i['link'] == j['link']:
                    count = 1
        if count == 1:
            c.remove(i)
    return c


# 读取记录
def readRss(name) -> dict:
    # 检查是否存在rss记录
    if not os.path.isfile(file_path + (name + '.json')):
        return {}
    with codecs.open(file_path + (name + ".json"), 'r', 'utf-8') as load_f:
        load_dict = json.load(load_f)
    return load_dict


# 写入记录
def writeRss(name: str, new_rss: dict, new_item: list = None):
    if new_item:
        max_length = len(new_rss.entries)
        # 防止 rss 超过设置的缓存条数
        if max_length >= config.limt:
            LIMT = max_length + config.limt
        else:
            LIMT = config.limt
        old = readRss(name)
        for tmp in new_item:
            old['entries'].insert(0, tmp)
        old['entries'] = old['entries'][0:LIMT]
    else:
        old = new_rss
    if not os.path.isdir(file_path):
        os.makedirs(file_path)
    with codecs.open(file_path + (name + ".json"), "w", 'utf-8') as dump_f:
        dump_f.write(json.dumps(old, sort_keys=True,
                                indent=4, ensure_ascii=False))


# 发送消息
async def sendMsg(rss: rss_class, msg: str) -> bool:
    bot, = nonebot.get_bots().values()
    try:
        if len(msg) <= 0:
            return False
        if rss.user_id:
            for id in rss.user_id:
                try:
                    await bot.send_msg(message_type='private', user_id=id, message=str(msg))
                except Exception as e:
                    logger.error('QQ号' + id + '不合法或者不是好友 E:' + str(e))

        if rss.group_id:
            for id in rss.group_id:
                try:
                    await bot.send_msg(message_type='group', group_id=id, message=str(msg))
                except Exception as e:
                    logger.info('群号' + id + '不合法或者未加群 E:' + str(e))
        return True
    except Exception as e:
        logger.info('发生错误 消息发送失败 E:' + str(e))
        return False
