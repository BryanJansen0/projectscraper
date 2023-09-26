from tenacity import retry, stop_after_attempt
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import json

from random import shuffle
from aiofiles import open
from pathlib import Path
from datetime import datetime as dt
from loguru import logger
import re
from asyncinit import asyncinit
from tqdm import tqdm
from models import AliProduct, DetailedListing, AliProductIdOnly, NewDetailedListing
from db import dbinit
from settings import get_config, Config
from beanie.operators import Eq
from parsel import Selector

logger.add(f"./logs/{dt.now().timestamp()}.log")

@asyncinit
class Ali:
    category: int
    cfg: Config
    browser: Browser
    context: BrowserContext
    page: Page
    total_scraped: int = 0

    async def __init__(self, headless: bool = True):
        self.cfg = get_config()
        session = "session.json"
        await dbinit()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.firefox.launch(
            headless=headless, timeout=60000
        )
        self.context = await self.browser.new_context(
            proxy={
                "server": "52.21.249.76:31112",
                "password": "6WCBj1aKuUpkG4z3_country-Romania",
                "username": "commercefy",
            },
            ignore_https_errors=True,
            storage_state=session if Path(session).exists() else None,
        )
        self.context.set_default_timeout(self.cfg.timeout)
        await self.context.add_cookies([self.cfg.ali_romanian_usd_cookies])
        self.page = await self.context.new_page()
        await self.page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["stylesheet", "image", "font"]
            else route.continue_(),
        )

    @retry(stop=stop_after_attempt(2))
    async def scrape_new_product(self, id: int):
        url = f"https://www.aliexpress.com/i/{id}.html"
        logger.info(f"scraping product {url=}")
        result = await self.page.goto(url)
        assert result.status == 200
        product_json = await self.page.evaluate("window.runParams")
        if len(product_json["data"].keys()) < 20:
            logger.error(f"No product data {url}")
        
        else:
            product = await AliProduct.get(id)
            async with open(f"./prods/p-{id}-{dt.now().timestamp()}.json", "w+") as f:
                await f.write(json.dumps(product_json))            
            product.detailed = NewDetailedListing(**product_json["data"]) #  <================== new
            keywords = await self.page.locator('meta[name="keywords"]').get_attribute(
                "content"
            )
            product.keywords = keywords
            # result = await self.page.goto(url.replace("item", "i"))
            # assert result.status == 200

            body = await self.page.content()

            sel = Selector(body)
            selling_points = sel.css('ul[class^="seo-sellpoints"] pre::text').getall()

            logger.warning(selling_points)
            product.selling_points = ", ".join(selling_points) if len(selling_points) else None
            await product.save()



    @retry(reraise=True, stop=stop_after_attempt(1))
    async def scrape_new_products(self):
        for _ in tqdm(range(await AliProductIdOnly.find(Eq(AliProduct.detailed, None)).count())):
            new = await AliProductIdOnly.find(Eq(AliProduct.detailed, None)).to_list()
            for item in new:
                await self.scrape_new_product(item.id)

async def main():
    ali = await Ali(headless=False)
    await ali.scrape_new_products()

    await ali.browser.close()
    await ali.playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
