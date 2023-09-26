from tenacity import retry, stop_after_attempt
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import json

from random import shuffle
from aiofiles import open
from math import ceil
from datetime import datetime as dt
from loguru import logger
from pathlib import Path
import urllib.parse
from asyncinit import asyncinit
from random import shuffle
from tqdm import tqdm
from models import AliProduct, DetailedListing
from db import dbinit
from settings import get_config, Config, get_filters, Filters
from beanie.operators import Eq

logger.add(f"./logs/{dt.now().timestamp()}.log")


# category-list => evaluation.starRating:4.7
# category-list => trade.tradeDesc:"47 sold"


# detailed.imageModule.imagePathList
# detailed.skuModule.skuPriceList[].skuVal.availQuantity:26
# detailed.storeModule.followingNumber
#                     .positiveRate:"96.4%"

# detailed.titleModule.subject / category-list => title.seoTitle
# detailed.pageModule.description
# detailed.pageModule.keywords
# storeModule.topRatedSeller == True


# detailed.data.shippingModule.generalFreightInfo.originalLayoutResultList []
# detailed hideShipFrom:true
# detailed.additionLayout → componentId 929 1189
# detailed.bizData.deliveryProviderName
# detailed.bizData.shipFrom
# detailed.bizData.deliveryDayMax 7
# detailed.deliveryOptionPanelDisplayList [str] → componentId 3042 - 7day delivery


@asyncinit
class Ali:
    category: int
    cfg: Config
    browser: Browser
    context: BrowserContext
    page: Page
    total_scraped: int = 0

    async def __init__(self, category: int, headless: bool = True):
        self.category = category
        self.cfg = get_config()
        session = "session.json"
        await dbinit()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.firefox.launch(headless=headless)
        self.context = await self.browser.new_context(  # proxy={"server":"127.0.0.1:8080"}, ignore_https_errors=True,
            # record_video_dir="videos/",
            # record_video_size=self.cfg.video,
            storage_state=session if Path(session).exists() else None,
        )
        self.context.set_default_timeout(self.cfg.timeout)
        await self.context.add_cookies([self.cfg.ali_romanian_usd_cookies])
        self.page = await self.context.new_page()

    async def parse_products(self, data: dict):
        ids = [x.id for x in await AliProduct.find_all().to_list()]
        # print(ids)
        items = (
            data["data"]["data"]["root"]["fields"]["mods"]
            .get("itemList", {})
            .get("content", [])
        )
        on_page = len(items)
        self.total_scraped += on_page
        logger.info(f"found {on_page=} products, total={self.total_scraped}")
        for item in tqdm(items):
            pid = int(item["productId"])
            if pid not in ids:
                logger.success(f"found smth new! {pid}")
                # print(item)
                x = await AliProduct(id=pid, in_category_list=item).save()
                # print(x)
            else:
                logger.info(pid)

    @retry(reraise=True, stop=stop_after_attempt(2))
    async def open_category_nth_page(
        self,
        url_model: str = None,
        n: int = 1,
        min_price: int = 0,
        max_price: int = 888,
        above_4_stars: bool = True,
        plus_only: bool = True,
    ):
        logger.debug(f"{n=}")
        if not url_model:
            params = {
                "CatId": self.category,
                "trafficChannel": "main",
                "isCategoryBrowse": True,
                "g": "y",  # grid, n for stack
                # "dida": "y",
                "page": n,
                "isFavorite": "y" if above_4_stars else "n",
                "isMall": "y" if plus_only else "n",
                "sortType":"total_tranpro_desc",
                # "catId": 0,
                "minPrice": int(min_price),
                "maxPrice": int(max_price),
                "isrefine": "y",
            }
            if n > 1:
                params["page"] = n
            query = urllib.parse.urlencode(params)
            url = (
                f"https://www.aliexpress.com/premium/category/{self.category}/{n}.html?{query}"
            )
        else:
            url = url_model.replace("/1.html", f"/{n}.html").replace(
                "page=1&", f"page={n}&"
            )
            logger.debug(url)
        # await self.page.route(
        #     "**/*",
        #     lambda route: route.abort()
        #     if route.request.resource_type == "image"
        #     else route.continue_(),
        # )            
        result = await self.page.goto(url)
        assert result.status == 200
        if (self.page.url != url) and not url_model:
            logger.warning(f"opened {url=}, got {result.url=}")
            result = await self.page.goto(f"{result.url}&{query}")
        category_json = await self.page.evaluate(self.cfg.dida)
        async with open(
            f"./categ/c-{self.category}-{n}-{dt.now().timestamp()}.json", "w+"
        ) as f:
            await f.write(json.dumps(category_json))
        # await self.page.screenshot(
        #     path=f"./screenshots/c-{self.category}-{n}-{dt.now().timestamp()}.png",
        #     full_page=True,
        # )
        return category_json, result.url

    @retry(reraise=True, stop=stop_after_attempt(4))
    async def scrape_category(self, filters: Filters):
        data, url_model = await self.open_category_nth_page(
            n=1,
            min_price=filters.min_price,
            max_price=filters.max_price,
            plus_only=filters.plus_only,
            above_4_stars=filters.min_prod_rating >= 4,
        )
        logger.info(url_model)
        page_info = data["data"]["data"]["root"]["fields"]["pageInfo"]
        total_products = page_info["totalResults"]
        page_size = page_info["pageSize"]

        if total_products:
            await self.parse_products(data)
            total_pages = ceil(total_products / page_size)
            logger.success(f"{total_products=} {page_size=} {total_pages=}")
            for n in tqdm(range(2, total_pages + 1)):
                data, _ = await self.open_category_nth_page(n=n, url_model=url_model)
                await self.parse_products(data)
        else:
            logger.error(f"no results for {self.category=}")
            


async def main(category: int):
    filters = get_filters()
    ali = await Ali(category=category, headless=False)
    await ali.scrape_category(filters)
    await ali.browser.close()
    await ali.playwright.stop()


if __name__ == "__main__":

    #todo = [200218548] # Solar https://www.aliexpress.com/category/200218548/solar.html
    # Solar Cells https://www.aliexpress.com/premium/category/52806/1.html
    # 200217419 # Projection screen  https://www.aliexpress.com/premium/category/200217419/1.html
    # https://www.aliexpress.com/w/wholesale-Manual-presses-and-juicers.html
    # https://www.aliexpress.com/category/200215731/Decanters.html
    # https://www.aliexpress.com/category/611/Juicers.html
    # https://www.aliexpress.com/category/100005634/Garden-Cultivator.html
    # 301102 https://www.aliexpress.com/w/wholesale-Surveillance-Cameras.html
    # shuffle(todo)


    # 4 April
    # 410401 Alternative Energy Generators (windmill generators)
    # 200217419 Projection screens

    for cat in [200217419]:
        asyncio.run(main(cat))
