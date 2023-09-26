from typing import Callable
import shopify

import asyncio
from tenacity import retry, stop_after_attempt
from configparser import ConfigParser
from tqdm import tqdm
from random import shuffle, sample
import re
from pyactiveresource.connection import ResourceNotFound
from time import sleep
from models import OptimisedInfo, Translations
from settings import removables
from requests import get
from models import OurProduct, Ean
from db import dbinit
from settings import get_config, Config
from beanie.operators import NE, Eq
from loguru import logger
from ratelimit import limits, sleep_and_retry
import sentry_sdk
from os.path import basename
from thefuzz import fuzz
from beanie.odm.enums import SortDirection
from datetime import datetime as dt


logger.add(f"./logs/{dt.now().timestamp()}.log")

sentry_sdk.init(
    "https://970f052a26d44b178c8cbc1f7144e419@o4504776258879488.ingest.sentry.io/4504776259665920",
    traces_sample_rate=1.0,
)
shop_url = "bryancommerce.myshopify.com"
api_version = "2023-01"
parser = ConfigParser()
CONFIG_FILE = 'config.ini'

ONE_MINUTE = 60


# @sleep_and_retry
# @limits(calls=120, period=ONE_MINUTE)

async def update_shopify(here: OurProduct, lang: OptimisedInfo, gpm: int = 100, log_func: Callable = logger):
    updated = False
    there = shopify.Product()
    if here.shopify_id:
        try:
            there = shopify.Product.find(id_=here.shopify_id)
        except Exception as e:
            log_func.error(e)
            there.attributes["title"] = here.optimised.title
            there.save()
            here.shopify_id = there.id
            await here.save()
    else:
        there.attributes["title"] = lang.title
        there.save()
        here.shopify_id = there.id
        await here.save()

    log_func.info(f"https://bryancommerce.myshopify.com/admin/products/{here.shopify_id} for https://aliexpress.com/i/{here.pid}.html")

    found_link = False
    ali_link = f'https://aliexpress.com/i/{here.pid}.html'
    try:
        if there.metafields_count():
            for mf in there.metafields():
                if mf.namespace == 'custom' and mf.key == 'link':

                    found_link = True
                    logger.info('checking link metafield')
                    if mf.value != ali_link:
                        logger.info('==> updating ali link')
                        mf.value = ali_link
                        mf.save()
                    else:
                        logger.info('==> ok')
    except:
        pass
    if not found_link:
        logger.info('adding ali link')
        mf = shopify.Metafield()
        mf.namespace = 'custom'
        mf.key = 'link'
        mf.value = ali_link
        there.add_metafield(mf)


    if here.vendor and (there.vendor != here.vendor):
        log_func.debug(
            f"Updating vendor from:\n{there.vendor}\nto\n{here.vendor}"
        )
        there.attributes['vendor'] = here.vendor
        there.vendor = here.vendor
        updated = True

    # if there.attributes["title"] != lang.title:
    #     log_func.info(
    #         f"Updating title from:\n{there.attributes['title']}\nto\n{lang.title}"
    #     )
    #     there.attributes["title"] = lang.title
    #     updated = True

    if fuzz.ratio(there.attributes["body_html"], lang.description + lang.specs or []) < 5:
        log_func.info("Refreshing description")
        logger.debug(there.attributes["body_html"])
        logger.debug('=============')
        logger.debug(lang.description + lang.specs)
        there.attributes["body_html"] = (
            lang.description.replace("\n", "<br />\n")
            + "<br /><br />"
            + "Specifications:"
            + "<ul><li>"
            + str(lang.specs).replace('\n', '</li><li>')
            + "</li></ul>"
        )
        updated = True

    if ("importedV2" not in there.attributes["tags"]) and ("importedV3" not in there.attributes["tags"]):
        # log_func.info(f"Refreshing tags")
        there.attributes["tags"] = ''.join(ch for ch in here.keywords if ch.isalnum()) + ",importedV3"
        updated = True

    w = None
    for x, y in here.specs:
        if "weight" in x.lower():
            try:
                w, u = re.findall("(\d+[.\d]*)(\w*)", y)[0]
                break
            except:
                pass
    if not w:
        log_func.warning("no weight in specifications")

    if here.category:
        if there.attributes["product_type"] != here.category:
            logger.info('updating category')
            there.attributes["product_type"] = here.category
            updated = True
    else:
        if not there.attributes["product_type"]:
            logger.info('adding special tag')
            there.attributes["product_type"] = "PLEASE CHECK V2"
            updated = True

    if updated:
        logger.success('saving')
        
        if not there.save():
            logger.error('problem when saving')
            logger.debug(there.__dict__)
            
        sleep(0.7)

    if not len(there.attributes["images"]):
        log_func.warning("Need to upload images")
        images = []

        for url in tqdm(here.images, colour="blue"):
            image = shopify.Image({"product_id": there.id})
            binary_in = get(url).content
            brand = re.compile(here.vendor + r"[-\s]*", re.IGNORECASE)
            remove = re.compile(removables, re.IGNORECASE)
            image.attach_image(
                data=binary_in, filename=remove.sub("", brand.sub("", basename(url)))
            )
            # image.src = str(url)
            result = image.save()
            sleep(1)
            log_func.info(f"image upload {result=}")

            images.append(image)

        there.attributes["images"] = images
        there.save()
        sleep(1)

    log_func.info(f"{here.shopify_id=} {here.ean=} {here.title=}")
    var_updated = False

    variant = there.variants[0]
    ii_id = variant.attributes["inventory_item_id"]
    ii = shopify.InventoryItem.find(id_=ii_id)
    if not ii.tracked:
        ii.tracked = True
        ii.save()
        sleep(0.5)

    inv = shopify.InventoryLevel.find(
        inventory_item_ids=ii_id,
        location_ids=74796990730,
    )[0]
    if inv.attributes['available'] != here.qty:
        log_func.warning(f'{here.shopify_id} inventory_item {variant.attributes["inventory_item_id"]} needs qty update')
        inv.set(74796990730, ii_id, here.qty)
        sleep(0.5)

    ean_in_db = await Ean.find_one(Ean.id == here.ean)

    if not here.ean or ean_in_db.prod_id != here.id:
        next_free_ean = await Ean.find_one(Eq(Ean.prod_id, None), limit=1)
        log_func.warning("issuing new ean")
        here.ean = next_free_ean.id
        await here.save()
        next_free_ean.prod_id = here.id
        await next_free_ean.save()
        # TODO free unused EANs

    if  int(variant.attributes["sku"] or 0) != here.ean:  # 
        variant.attributes["sku"] = here.ean  # <=========== int
        var_updated = True

    if  int(variant.attributes["barcode"] or 0) != here.ean:  # <=========== int
        variant.attributes["barcode"] = here.ean
        var_updated = True


    target_price = round(2 * (here.price/123*100 + here.shipping) * gpm / 100, 2)
    if round(float(variant.attributes["price"]),2) != target_price:
        log_func.warning(f'updating current Shopify price from {variant.attributes["price"]} to {target_price}, {gpm=}, db_price={round(2 * (here.price/123*100 + here.shipping) * gpm / 100, 2)} {here.price=} {here.shipping=} formula=2*(sku.price/123*100+sku.shipping)')
        variant.attributes["price"] = target_price
        var_updated = True

    if w:
        if str(variant.attributes.get("weight")) != w:
            variant.attributes["weight"] = w
            var_updated = True

        if u and (variant.attributes.get("weight_unit") != u):
            variant.attributes["weight_unit"] = u
            var_updated = True

    if var_updated:
        variant.save()
        sleep(0.5)

    there.save()
    sleep(0.5)


async def main(cfg: Config):
    parser.read(CONFIG_FILE)
    session = shopify.Session(shop_url, api_version, cfg.shopify.shpat, )
    shopify.ShopifyResource.activate_session(session)
    # coll = shopify.CustomCollection.find(id_=495902916874)
    await dbinit()
    # for prod in tqdm(await OurProduct.find(NE(OurProduct.optimised, None), NE(OurProduct.translations, None), limit=5).to_list(), colour='green'):
    products = await OurProduct.find(NE(OurProduct.optimised, None), NE(OurProduct.optimised.specs, None),).sort((OurProduct.added, SortDirection.DESCENDING)).to_list()
    # gpm = int(parser.get('multiplier', 'value'))
    gpm = 100
    shuffle(products)
    for prod in tqdm(products,
        colour="green",
    ):  
        try:
            await update_shopify(prod, prod.optimised, gpm=gpm, log_func=logger)
        except KeyError as e:
            logger.error(prod)
            continue

        # _ = input('continue?')
    shopify.ShopifyResource.clear_session()


if __name__ == "__main__":
    asyncio.run(main(get_config()))
