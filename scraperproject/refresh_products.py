from tenacity import retry, stop_after_attempt, wait_fixed
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import json

from random import shuffle
from devtools import debug
from aiofiles import open
from math import ceil
from datetime import datetime as dt
from loguru import logger
import re
from asyncinit import asyncinit
from random import shuffle
from tqdm import tqdm
from models import OurProduct, DetailedListing, NewDetailedListing
from db import dbinit
from settings import get_config, Config, get_filters, Filters
from beanie.operators import Eq

logger.add(f"./logs/{dt.now().timestamp()}.log")

# get product ids + sku ids from clean
# rescrape them


BAD_STORES = [900185004, 911381190, 3280019, 5731187]

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
        await dbinit()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.firefox.launch(
            headless=headless, timeout=60000
        )
        self.context = await self.browser.new_context(    proxy={"server":"http://52.202.135.176:31112", "username":"commercefy", "password":"6WCBj1aKuUpkG4z3"}, ignore_https_errors=True,
            # record_video_dir="videos/",
            # record_video_size=self.cfg.video,
            # record_har_path="./playwright_test_noimg.har"
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


    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_fixed(5))
    async def refresh_clean_product(self, product: OurProduct, filters: Filters):
        url = f"https://www.aliexpress.com/item/{product.id}.html"

        logger.info(f"REscraping product {url}")
        logger.info(
            f"https://bryancommerce.myshopify.com/admin/products/{product.shopify_id}"
        )
        logger.debug(
            f"query in dbgate -->>   db.collection('clean').find({{_id: {product.id} }})"
        )

        result = await self.page.goto(url)
        assert result.status == 200

        # await self.page.screenshot(
        #     path=f"./screenshots/p-{id}-{dt.now().timestamp()}.png", full_page=True
        # )
        product_json = await self.page.evaluate("window.runParams")

        if product_json is  None:
            logger.error(f"{url}, 'No product data' ")
            return

        if len(product_json["data"].keys()) < 20:
            logger.error(f"{url}, 'No product data'")
            # raise Exception("No product data")
        else:
            if not product.skip:
                skus = {sku.id: sku for sku in product.ali.skus}
                logger.debug(f"{skus.keys()=}")
                # debug(product_json["data"])
                #-----------------------------------------------------
                # old!
                # detailed = DetailedListing(**product_json["data"])
                #
                # variants = detailed.skuModule.get("skuPriceList", [])
                #------------------------------------------------------
                # new!
                detailed = NewDetailedListing(**product_json["data"])
                variants = detailed.priceComponent.get('skuPriceList', [])
                logger.info(f"{len(variants)} skus before country filtering")

                variants = filter(
                    lambda x: "201336100" not in x["skuAttr"]
                    and "201441035" not in x["skuAttr"],
                    variants,
                )  # exclude China stock
                variants = filter(
                    lambda x: "203124902" not in x["skuAttr"], variants
                )  # exclude UAE stock
                variants = filter(
                    lambda x: "201336106" not in x["skuAttr"], variants
                )  # exclude USA stock
                variants = filter(
                    lambda x: "201336105" not in x["skuAttr"], variants
                )  # exclude UK stock
                variants = filter(
                    lambda x: "201336103" not in x["skuAttr"], variants
                )  # exclude Russia stock
                variants = filter(
                    lambda x: "100014852" not in x["skuAttr"], variants
                )  # exclude Canada stock
                variants = filter(
                    lambda x: "203054829" not in x["skuAttr"], variants
                )  # exclude Brazil stock

                variants = list(variants)
                logger.info(f"{len(variants)} skus after country filtering")

                variants = filter(
                    lambda x: "20660849" not in x["skuAttr"], variants
                )  # exclude US plug
                variants = filter(
                    lambda x: "201447605" not in x["skuAttr"], variants
                )  # exclude US plug
                variants = filter(
                    lambda x: "201447607" not in x["skuAttr"], variants
                )  # exclude UK plug                


                variants = list(variants)
                logger.info(f"{len(variants)} skus after US plug excluding")

                for variant in variants:
                    # logger.debug(f"{variant=}")
                    data = json.loads(variant["freightExt"])
                    if sku := skus.get(variant["skuId"]):
                        sku.price = float(data["p1"])
                        sku.qty = (
                            variant["skuVal"].get("availQuantity", 0)
                            if variant["salable"]
                            else 0
                        )
                        logger.info(f"sku_id: {variant['skuIdStr']} | price: {sku.price} | Amount: {sku.qty}")
                    else:
                        pass
                        # create new variant here

                for sku_id in skus.keys():
                    if sku_id not in [variant["skuId"] for variant in variants]:
                        sku = skus[sku_id]
                        sku.qty = 0
            if product.skip or product.store in BAD_STORES:
                for sku in product.ali.skus:
                    sku.qty = 0
                if "skip_as_disabled" not in product.ali.keywords:
                    product.ali.keywords += ",skip_as_disabled"

            await product.save()

        async with open(f"./prods/p-{id}-{dt.now().timestamp()}.json", "w+") as f:
            await f.write(json.dumps(product_json))


async def main():
    filters = get_filters()
    ali = await Ali(headless=True)

    products = await OurProduct.find().to_list()
    shuffle(products)

    for prod in tqdm(products, colour="green"):
        await ali.refresh_clean_product(prod, filters)

    await ali.context.close()
    await ali.browser.close()
    await ali.playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
