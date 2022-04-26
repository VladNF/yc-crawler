#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import itertools as it
import logging
import mimetypes
import os
import re
from optparse import OptionParser
from collections import namedtuple
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup as BS

ROOT_URL = "https://news.ycombinator.com/"
ROOT_DATA = "./data/"
MAX_CONN_PER_HOST = 1
FETCH_TIMEOUT = 10
FETCH_PERIOD = 4 * 60
News = namedtuple("News", "id name url")


def directory_exists(dir_name):
    path = os.path.join(ROOT_DATA, dir_name)
    return os.path.exists(path)


def save_binary(dir_name, file_name, data):
    path = os.path.join(ROOT_DATA, dir_name)
    if not os.path.exists(path):
        os.makedirs(path)
    path = os.path.join(path, file_name)

    with open(path, "wb") as fp:
        fp.write(data)


async def async_save_binary(loop, path, fname, data):
    await loop.run_in_executor(None, save_binary, path, fname, data)


async def download_page(session, url):
    logging.debug(f"Entered download_page: url -- {url}")
    async with session.get(url) as response:
        logging.info(f"Started downloading: url  -- {url}")
        return await response.read(), url


def extract_news_from_index(html):
    soup = BS(html, "lxml")
    blocks = soup.find_all("tr", class_="athing", limit=30)
    for block in blocks:
        story_id = block["id"]
        story_tag = block.find("a", class_="titlelink")
        story_name = story_tag.string
        story_url = story_tag["href"]
        yield News(story_id, story_name, story_url)


def get_valid_filename(s):
    s = str(s).strip().replace(" ", "_")
    return re.sub(r"(?u)[^-\w.]", "", s)


async def download_one_news(loop, session, news):
    logging.info(f"Started fetching news {news}")

    if directory_exists(news.id):
        logging.info(
            f"It seems the news {news} has already been downloaded... Skipping it."
        )
        return

    # download news by url
    try:
        news_body, _ = await download_page(session, news.url)
    except Exception:
        logging.error(f"Error when downloading news page with {news.url}", exc_info=1)
        raise

    # save news in a folder
    mtype, _ = mimetypes.guess_type(news.url)
    fname = news.url.split("/")[-1] if mtype else news.name + ".html"
    try:
        fname = get_valid_filename(fname)[:128]
        await async_save_binary(loop, news.id + "/", fname, news_body)
    except Exception:
        logging.error(f"Error when saving {news} to file {fname}", exc_info=1)
        raise

    # download comments
    try:
        await download_from_comments(loop, session, news)
    except Exception:
        logging.error(f"Error when processing comments for {news}", exc_info=1)
        raise

    logging.info(f"Finished fetching news {news}")


def extract_urls_from_comments(news, comments_body):
    soup = BS(comments_body, "lxml")
    comments_tree = soup.find("table", class_="comment-tree")
    if not comments_tree:
        logging.info(f"No comments for news {news.id} yet!")
        return []
    comments = comments_tree.find_all("div", class_="comment")
    atags = [[a for a in c.find_all("a") if a.string != "reply"] for c in comments]
    return [a["href"] for a in it.chain(*atags)]


async def download_from_comments(loop, session, news):
    logging.info(f"Started fetching comments for news {news}")
    comment_url = f"{ROOT_URL}item?id={news.id}"
    try:
        comments_body, _ = await download_page(session, comment_url)
    except Exception:
        logging.error(
            f"Error when downloading comments page with {comment_url}", exc_info=1
        )
        raise

    urls = extract_urls_from_comments(news, comments_body)
    tasks = [download_page(session, url) for url in urls]
    for f in asyncio.as_completed(tasks):
        try:
            content, url = await f
            logging.debug(f"News {news.id}: downloaded from comments -- {url}")
            mtype, _ = mimetypes.guess_type(url)
            ix = -2 if url.endswith("/") else -1
            if mtype:
                fname = url.split("/")[ix]
            else:
                tnode = BS(content, "lxml").title
                title = tnode.string if tnode else url.split("/")[ix]
                fname = title + ".html"

            fname = get_valid_filename(fname)[:128]
            await async_save_binary(loop, news.id + "/", fname, content)
        except Exception:
            logging.error(
                f"Error when downloading linked materials from comments for {news}",
                exc_info=1,
            )

    logging.info(f"Finished fetching comments for news {news}")


async def download_news(loop):
    connector = aiohttp.TCPConnector(
        limit=MAX_CONN_PER_HOST * 30, limit_per_host=MAX_CONN_PER_HOST
    )
    timeout = aiohttp.ClientTimeout(sock_read=FETCH_TIMEOUT, sock_connect=FETCH_TIMEOUT)
    async with aiohttp.ClientSession(
        connector=connector, loop=loop, timeout=timeout
    ) as session:
        index_body, _ = await download_page(session, ROOT_URL)
        tasks = [
            download_one_news(loop, session, news)
            for news in extract_news_from_index(index_body)
        ]
        for f in asyncio.as_completed(tasks):
            try:
                _ = await f
            except Exception:
                logging.error(f"Error when processing news", exc_info=1)


def main(loop, period):
    logging.info("Started a crawling iteration...")

    # await news crawling coroutine
    task = asyncio.create_task(download_news(loop))
    now = datetime.now()

    def callback(f):
        logging.info(
            "> Finished a crawling iteration which took "
            f"{(datetime.now() - now).total_seconds():.2f} seconds"
        )

    task.add_done_callback(callback)
    logging.info(f"Waiting for {period} seconds...")

    # schedule next run in period of seconds
    loop.call_later(period, main, loop, period)


if __name__ == "__main__":
    op = OptionParser()
    op.add_option("-l", "--log", action="store", default=None)
    op.add_option(
        "-w", "--workers", action="store", type="int", default=MAX_CONN_PER_HOST
    )
    op.add_option("-v", "--verbose", action="store_true", default=False)
    op.add_option("-r", "--root", action="store", default=ROOT_DATA)
    op.add_option("-p", "--period", action="store", default=FETCH_PERIOD)

    opts, args = op.parse_args()
    ROOT_DATA = opts.root
    MAX_CONN_PER_HOST = opts.workers

    logging.basicConfig(
        filename=opts.log,
        level=logging.INFO if not opts.verbose else logging.DEBUG,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S",
    )

    logging.info("YCombinator crawler started with options: %s" % opts)
    loop = asyncio.get_event_loop()
    try:
        loop.call_soon(main, loop, opts.period)
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.exception("Unexpected error: %s" % e)
    finally:
        loop.close()
    logging.info("YCombinator crawler has finished")
