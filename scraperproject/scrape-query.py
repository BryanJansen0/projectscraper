from tenacity import retry, stop_after_attempt
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import json

from aiofiles import open
from math import ceil
from datetime import datetime as dt
from loguru import logger
from pathlib import Path
import urllib.parse
from asyncinit import asyncinit
from tqdm import tqdm
from models import AliProduct
from db import dbinit
from settings import get_config, Config, get_filters, Filters

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
    query: str
    cfg: Config
    browser: Browser
    context: BrowserContext
    page: Page
    total_scraped: int = 0

    async def __init__(self, query: str, headless: bool = True):
        self.query = query
        self.cfg = get_config()
        session = "session.json"
        await dbinit()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.firefox.launch(headless=headless)
        self.context = await self.browser.new_context(
            proxy={
                "server": "54.146.26.143:31112",
                "password": "6WCBj1aKuUpkG4z3_country-Romania",
                "username": "commercefy",
            },
            ignore_https_errors=True,
            # record_video_dir="videos/",
            # record_video_size=self.cfg.video,
            record_har_path="./april_7_q_slim.har",
            storage_state=session if Path(session).exists() else None,
        )
        self.context.set_default_timeout(self.cfg.timeout)
        await self.context.add_cookies([self.cfg.ali_romanian_usd_cookies])
        self.page = await self.context.new_page()
        await self.page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["stylesheet", "script", "image", "font"]
            else route.continue_(),
        )

    async def parse_products(self, data: dict):
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
            if not await AliProduct.get(pid):
                logger.success(f"found smth new! {pid}")
                new_ali = AliProduct(id=pid, in_category_list=item, category_query=self.query)
                _ = await new_ali.save()
                
            else:
                logger.info(f"already in database {pid=}")

    @retry(reraise=True, stop=stop_after_attempt(2))
    async def open_query_nth_page(
        self,
        n: int = 1,
        min_price: int = 0,
        max_price: int = 888,
        above_4_stars: bool = True,
        plus_only: bool = True,
    ):
        logger.debug(f"opening page {n=}")

        params = {
            # "CatId": self.category,
            "SearchText": self.query.replace(" ", "+"),
            "trafficChannel": "main",
            # "isCategoryBrowse": True,
            "g": "y",  # grid, n for stack
            # "dida": "y",
            "page": n,
            "isFavorite": "y" if above_4_stars else "n",
            "isMall": "y" if plus_only else "n",
            "sortType": "total_tranpro_desc",
            # "catId": 0,
            "minPrice": int(min_price),
            "maxPrice": int(max_price),
            # "isrefine": "y",
        }
        query = urllib.parse.urlencode(params)
        url = f"https://www.aliexpress.com/wholesale?{query}"
        logger.debug(f"{url=}")
        result = await self.page.goto(url)
        assert result.status == 200
        if self.page.url != url:
            logger.warning(f"{result.url=}")
        query_json = await self.page.evaluate(self.cfg.dida)
        async with open(
            f"./qpage/q-{self.query.replace(' ', '_')}-{n}-{dt.now().timestamp()}.json",
            "w+",
        ) as f:
            await f.write(json.dumps(query_json))
        return query_json

    @retry(reraise=True, stop=stop_after_attempt(4))
    async def scrape_query(self, filters: Filters):
        data = await self.open_query_nth_page(
            min_price=filters.min_price,
            max_price=filters.max_price,
            plus_only=filters.plus_only,
            above_4_stars=filters.min_prod_rating >= 4,
        )
        page_info = data["data"]["data"]["root"]["fields"]["pageInfo"]
        total_products = page_info["totalResults"]
        page_size = page_info["pageSize"]

        if total_products:
            await self.parse_products(data)
            total_pages = ceil(total_products / page_size)
            logger.success(f"{total_products=} {page_size=} {total_pages=}")
            for n in tqdm(range(2, total_pages + 1)):
                data = await self.open_query_nth_page(
                    n=n,
                    min_price=filters.min_price,
                    max_price=filters.max_price,
                    plus_only=filters.plus_only,
                    above_4_stars=filters.min_prod_rating >= 4,
                )
                await self.parse_products(data)
        else:
            logger.error(f"no results for {self.query=}")


async def main(query: str):
    filters = get_filters()
    ali = await Ali(query=query, headless=True)
    await ali.scrape_query(filters)
    await ali.browser.close()
    await ali.playwright.stop()


if __name__ == "__main__":
    for q in [
        # "garden", "hiking", 
        "swimming"
    ]:
        asyncio.run(main(q))
