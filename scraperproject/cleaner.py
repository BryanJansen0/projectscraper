from functools import lru_cache
import json

import asyncio
from faker import Faker
import re
from requests import get
from tenacity import retry
from models import (
    SKU,
    AliProduct,
    OurProduct,
    AliInfo,
    OptimisedInfo,
    Translations,
    AliProductIdOnly,
    OurProductIdOnly
)
from db import dbinit
from random import sample
from settings import get_config, Config, get_filters, Filters, OpenAI, removables
from beanie.operators import Eq, NE, And, Not, Or
from loguru import logger
from tqdm import tqdm
from datetime import datetime as dt

from beanie.operators import Set, In, ElemMatch, NotIn, LTE
from parsel import Selector
import openai
from ratelimit import limits, sleep_and_retry

fake = Faker()

ONE_MINUTE = 60
PROP_SHIPS_FROM = 200007763

logger.add(f"./logs/cleaner-{dt.now().timestamp()}.log")


@sleep_and_retry
@limits(calls=100, period=ONE_MINUTE)
async def text_complete(
        prompt: str,
        oai: OpenAI,
        max_tokens: int = 50,
        temper: float = 0.03,
        model: str = "text-davinci-003",
) -> str:
    logger.debug(f"> {prompt}")
    # openai.organization = oai.org
    openai.api_key = oai.key
    r = await openai.Completion.acreate(
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temper,
    )

    response = r["choices"][0]["text"].strip()
    logger.debug(f"RESPONSE: (length={len(response)})")
    logger.debug(response)
    logger.debug("\n" in response)
    return response


# @sleep_and_retry
# @limits(calls=100, period=ONE_MINUTE)
async def gpt_complete(
        prompt: str,
        oai: OpenAI,
        max_tokens: int = 50,
        temper: float = 0.03,
        model: str = "gpt-3.5-turbo",
) -> str:
    logger.debug(f"> {prompt}")
    # openai.organization = oai.org
    openai.api_key = oai.key
    r = await openai.ChatCompletion.acreate(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )

    response = re.sub(r'\[vendor name\]', 'our store', r["choices"][0]["message"]["content"].strip(), flags=re.IGNORECASE)
    logger.debug(f"RESPONSE: (length={len(response)})")
    logger.debug(response)
    logger.debug("\n" in response)
    return response


# TODO: везде где используются сравнения в filter_dirty_products() уточить субмодели в models/NewDetailed...

async def filter_dirty_products(filters: Filters) -> list[AliProduct]:
    avoid = [322, 31008, 32003, 32004, 32005, 32813, 40505, 40509, 3280502, 100001606, 100001615, 100003070, 100003084,
             100003086, 100003088, 100003109, 100003141, 100003235, 100003269, 100003270, 100005624, 100005735,
             100005790, 100005791, 100005792, 100005793, 100005823, 200000347, 200000595, 200000598, 200000599,
             200000600, 200000601, 200000609, 200000613, 200000617, 200000625, 200000662, 200000668, 200000673,
             200000692, 200000701, 200000707, 200000708, 200000709, 200000724, 200000732, 200000741, 200000743,
             200000769, 200000773, 200000775, 200000777, 200000781, 200000782, 200000783, 200000785, 200000801,
             200000961, 200001092, 200001520, 200001532, 200001553, 200001554, 200001556, 200001648, 200001996,
             200002124, 200002136, 200002155, 200002161, 200002164, 200002253, 200003345, 200003450, 200003482,
             200003491, 200005118, 200033142, 200033143, 200034143, 200003613, 200118008, 200118010, 200128143,
             200215336, 200215341, 200216391, 200216407, 200216733, 200222143, 201230622, 201932007, 205776616,
             205778115, 205779615, 205780114, 205780509, 205842201, 205871601, 205874801, 205876401, 205895301,
             205900902, 205927403, 206081401, 206083901]
    # vevor = In(
    #     AliProduct.detailed.storeModule.storeNum,
    #     [4614008, 1802235, 912161326, 912168161, 912155350], # Vevor
    # )

    detailed_nonempty = And(AliProduct.detailed != None,
                            {"detailed.categoryComponent.secondLevelCategoryId": {"$nin": avoid}})
    all_dirty = AliProduct.find(detailed_nonempty)
    # all_dirty_vevor = AliProduct.find(detailed_nonempty, vevor)
    # logger.info(f"All dirty: {await all_dirty.count()} Vevor: {await all_dirty_vevor.count()}")
    logger.info(f"All dirty: {await all_dirty.count()}")

    rating_nonempty = And(AliProduct.detailed.feedbackComponent != None, detailed_nonempty)
    rating_exists = AliProduct.find(rating_nonempty)
    # rating_exists_vevor = AliProduct.find(rating_nonempty, vevor)
    # logger.info(f"Rating exists: {await rating_exists.count()} Vevor: {await rating_exists_vevor.count()}")
    logger.info(f"Rating exists: {await rating_exists.count()}")

    # VEVOR_RELAXED_RATING = 3

    rating_filter_all = AliProduct.detailed.feedbackComponent.evarageStar >= str(filters.min_prod_rating)
    # rating_filter_vevor = And(AliProduct.detailed.titleModule.feedbackRating.averageStar >= VEVOR_RELAXED_RATING, vevor)
    # rating_filter = And(rating_nonempty, Or(rating_filter_all, rating_filter_vevor))
    rating_filter = And(rating_nonempty, rating_filter_all)
    rating_ok = AliProduct.find(rating_filter)
    # rating_ok_vevor = AliProduct.find(And(rating_nonempty, rating_filter_vevor))
    # logger.info(
    #     f"Rating >={filters.min_prod_rating}: {await rating_ok.count()}  Vevor (rating >={VEVOR_RELAXED_RATING}): {await rating_ok_vevor.count()}"
    # )
    logger.info(
        f"Rating >={filters.min_prod_rating}: {await rating_ok.count()}"
    )

    # VEVOR_RELAXED_SALES = 0

    sold_number_filter_all = AliProduct.detailed.tradeComponent.formatTradeCount >= str(filters.min_orders)
    # sold_number_filter_vevor = And(AliProduct.detailed.titleModule.tradeCount >= VEVOR_RELAXED_SALES, vevor)
    # sold_number_filter = And(rating_filter, Or(sold_number_filter_all, sold_number_filter_vevor))
    sold_number_filter = And(rating_filter, sold_number_filter_all)
    number_sold_ok = AliProduct.find(sold_number_filter)
    # number_sold_ok_vevor = AliProduct.find(And(rating_filter, sold_number_filter_vevor))
    # logger.info(f"Total orders >= {filters.min_orders}: {await number_sold_ok.count()} Vevor >= {VEVOR_RELAXED_SALES}: {await number_sold_ok_vevor.count()}")
    logger.info(f"Total orders >= {filters.min_orders}: {await number_sold_ok.count()}")

    images_ok = AliProduct.detailed.imageComponent.imagePathList != None
    assert await AliProduct.find(images_ok).count() == await AliProduct.find(rating_nonempty).count()

    store_rating_filter_all = AliProduct.detailed.storeFeedbackComponent.sellerPositiveRate >= str(
        filters.min_store_rating)
    store_rating_filter = And(sold_number_filter, store_rating_filter_all)
    store_rating_ok = AliProduct.find(store_rating_filter)
    # store_rating_ok_vevor = AliProduct.find(And(sold_number_filter, store_rating_filter_all, vevor))
    # logger.info(f"Store rating >= {filters.min_store_rating}: {await store_rating_ok.count()} Vevor: {await store_rating_ok_vevor.count()}")
    logger.info(f"Store rating >= {filters.min_store_rating}: {await store_rating_ok.count()}")

    store_followers_filter_all = AliProduct.detailed.wishListComponent.storeWishedCount >= filters.min_store_followers
    store_followers_filter = And(store_rating_filter, store_followers_filter_all)
    store_followers_filter_ok = AliProduct.find(store_followers_filter)
    # store_followers_filter_vevor = AliProduct.find(And(store_rating_filter, store_followers_filter_all, vevor))
    # logger.info(f"Store followers: {await store_followers_filter_ok.count()} Vevor: {await store_followers_filter_vevor.count()}")
    logger.info(f"Store followers: {await store_followers_filter_ok.count()}")

    stock_qty_filter1 = (
            AliProduct.detailed.inventoryComponent.totalAvailQuantity >= filters.min_stock
    )
    stock_qty_filter2 = (
            AliProduct.detailed.inventoryComponent.totalAvailQuantity <= filters.max_stock
    )
    stock_qty_filter_all = And(stock_qty_filter1, stock_qty_filter2)
    stock_qty_filter = And(store_followers_filter, stock_qty_filter_all)
    stock_qty_ok = AliProduct.find(stock_qty_filter)
    # stock_qty_vevor = AliProduct.find(And(store_followers_filter, stock_qty_filter_all, vevor))
    # logger.info(f"Stock qty ok: {await stock_qty_ok.count()} Vevor: {await stock_qty_vevor.count()}")
    logger.info(f"Stock qty ok: {await stock_qty_ok.count()}")
    
    delivery = {
        "detailed.webGeneralFreightCalculateComponent.originalLayoutResultList": {
            "$elemMatch": {
                "bizData.shipFromCode": {"$nin": filters.shipping_from_avoid},
                "bizData.deliveryDayMax": {"$lte": filters.max_delivery},
            }
        }
    }
    
    delivery_filter = And(stock_qty_filter, delivery)
    delivery_ok = AliProduct.find(delivery_filter)
    # delivery_vevor = AliProduct.find(And(stock_qty_filter, delivery, vevor))
    delivery_count = await delivery_ok.count()
    # logger.info(f"Delivery up to {filters.max_delivery} days and NOT from {filters.shipping_from_avoid} filter: {delivery_count} Vevor: {await delivery_vevor.count()}")
    logger.info(
        f"Delivery up to {filters.max_delivery} days and NOT from {filters.shipping_from_avoid} filter: {delivery_count}")

    filtered = await delivery_ok.project(AliProductIdOnly).to_list()

    if delivery_count:
        logger.success("Please check randomly:")
        logger.success(
            sample([
                f"https://aliexpress.com/i/{x.id}.html"
                for x in filtered
            ], 5)
        )

    return filtered


# @retry
async def save_as_clean(filtered: list[AliProduct]) -> list[OurProduct]:
    filters = get_filters()

    existing_clean = await OurProduct.find().project(OurProductIdOnly).to_list()
    existing_clean_ids = [prod.pid for prod in existing_clean]

    filtered = [prod for prod in filtered if prod.id not in existing_clean_ids]

    filtered = await AliProduct.find(In(AliProduct.id, [x.id for x in filtered])).to_list()

    for prod in tqdm(filtered):
        logger.debug(f'working on https://aliexpress.com/i/{prod.id}.html')
        ptitle = prod.detailed.productInfoComponent.get('subject')
        logger.debug(f'{ptitle=}')

        try:
            r = get(
                url=prod.detailed.productDescComponent.get("descriptionUrl"),
                headers={"user-agent": fake.user_agent()},
            )
            assert r.status_code == 200
        except:
            continue
        html = Selector(r.text)
        description = html.xpath(
            '//*[not(self::script)][not(self::style)][not(contains(@style, "display:none"))]/text()'
        ).getall()

        description = "\n".join(filter(None, map(str.strip, description)))

        images = prod.detailed.imageComponent.imagePathList[0:6]

        category = prod.category_query

        shipping = [
            (
                x.bizData.deliveryDayMax,
                x.bizData.displayAmount,
                x.bizData.shipFromCode,
                x.bizData.deliveryProviderCode,
            )
            for x in filter(
                lambda z: 
                    z.bizData.shipFromCode
                    not in filters.shipping_from_avoid
                
                and 
                    z.bizData.deliveryDayMax
                    <= filters.max_delivery

                ,
                prod.detailed.webGeneralFreightCalculateComponent.originalLayoutResultList,
            )
        ]

        if not shipping:
            logger.error('no shipping matching filters')
            continue
        best_shipping = list(sorted(shipping, key=lambda x: x[0]))[0]
        logger.debug(f"{best_shipping=}")

        # 201336100, 201441035 China   CN
        # 203124902 UAE     AE
        # 201336106 USA     US
        # 201336105 UK      UK
        # 201336103 Russia  RU
        # 100014852 Canada  CA
        # 201336099 Austria AU
        # 201336101 Germany DE
        # 203054829 Brazil BR
        skus = []

        variants = prod.detailed.priceComponent.get("skuPriceList", [])
        properties = prod.detailed.skuComponent.get("productSKUPropertyList", [])
        logger.info(f"{len(variants)} skus before country filtering")
        variants = filter(lambda x: x["salable"], variants)
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
        logger.info(f"{len(variants)} skus after US/UK plug excluding")

        variants = filter(
            lambda x: x["skuVal"].get("availQuantity", 0), variants
        )  # exclude zero stock

        variants = list(variants)
        logger.info(f"{len(variants)} skus after zero-quantity filtering")

        # variants = sorted(variants, key=lambda x:x["skuVal"].get(
        #         "skuActivityAmount", x["skuVal"][ "skuAmount"]
        #     )["value"], reverse=True)

        for variant in variants:
            logger.debug(f"processing {variant=}")
            data = json.loads(variant["freightExt"])
            variant["title"] = ""
            attribs = variant["skuAttr"]
            # variant["loc"] = data["p8"]
            variant["price"] = data["p1"]
            variant["qty"] = variant["skuVal"].get("availQuantity", 0)
            variant["images"] = set()
            variant["attribs"] = {}

            for attrib in attribs.split(";"):
                attrib_name, attrib_val = attrib.split(":")
                if "#" in attrib_val:
                    attrib_val, title = attrib_val.split('#')
                    variant['title'] += f'{title} '
                logger.debug(f"{attrib_name=} {attrib_val=} {variant['title']=}")

                if attrib_name not in ["200007763"]:
                    variant["attribs"][int(attrib_name)] = int(attrib_val)

            for prop in properties:
                if prop["skuPropertyId"] in variant["attribs"].keys():
                    for propvalue in prop["skuPropertyValues"]:
                        if (
                                propvalue["propertyValueIdLong"]
                                == variant["attribs"][prop["skuPropertyId"]]
                        ):
                            # logger.critical(f"{prop=}")
                            # logger.warning(f"{propvalue=}")
                            if variant["title"] == "Default Variant":
                                variant["title"] = propvalue.get(
                                    "propertyValueDisplayName",
                                    propvalue.get(
                                        "skuPropertyValueTips",
                                        propvalue.get(
                                            "propertyValueDefinitionName",
                                            propvalue["skuPropertyTips"],
                                        ),
                                    ),
                                )
                            logger.debug(f"Got {variant['title']=}")
                            variant["images"].add(
                                propvalue.get("skuPropertyImagePath", None)
                            )

            variant["images"] = list(filter(None, variant["images"]))

        # variants = filter(lambda var: var["loc"] == best_shipping[2], variants)

        for variant in variants:
            print(
                variant["title"],
                # variant["loc"],
                variant["qty"],
                variant["price"],
                variant["attribs"],
            )

            skus.append(
                SKU(
                    image=variant["images"][0] if variant["images"] else None,
                    id=variant["skuId"],
                    qty=variant["qty"],
                    price=variant["price"],
                    # location=variant["loc"],
                    title=variant["title"],
                    shipping=best_shipping[1],
                )
            )

        specs = [
            (i.get("attrName"), i.get("attrValue"))
            for i in prod.detailed.productPropComponent.props
        ]

        specs = [
            (x, y)
            for x, y in specs
            if ("is_customized" not in x)
               and ("brand" not in x.lower())
               and ("china" not in y.lower())
        ]

        vendor = ""
        for spec in prod.detailed.productPropComponent.props:
            if "brand" in spec.get("attrName", "").lower():
                vendor = spec.get("attrValue", "")
                break

        if vendor:
            brand = re.compile(vendor + r"[-\s]*", re.IGNORECASE)
            ptitle = brand.sub("", ptitle)
            description = brand.sub("", description)
        else:
            logger.warning(f"{prod.id=} No apparent vendor/brand info")

        ptitle = re.compile(removables, re.IGNORECASE).sub("", ptitle)
        description = re.compile(removables, re.IGNORECASE).sub("", description)

        keywords = prod.keywords or ""
        selling_points = prod.selling_points or ""

        bag = set({})
        for sku in skus:
            if sku.title not in bag:
                bag.add(sku.title)
                await OurProduct(
                    qty=sku.qty,
                    price=sku.price,
                    title=ptitle + ' ' + sku.title,
                    description=description,
                    vendor=vendor,
                    specs=specs,
                    images=images,
                    pid=prod.id,            
                    id=sku.id,
                    category=category,            
                    store=int(prod.detailed.sellerComponent.storeNum),
                    keywords=keywords.lower()
                    .replace(vendor.lower(), "")
                    .replace("aliexpress.com", "")
                    .replace("aliexpress", "")
                    .replace(str(prod.id), ""),
                    selling_points=selling_points.lower().replace(vendor.lower(), ""),
                ).save()


async def update_titles(oai: OpenAI) -> list[OurProduct]:
    openai.organization = oai.org
    openai.api_key = oai.key

    # async for prod in OurProduct.find(NE(OurProduct.optimised, None),
    #     # OurProduct.shopify_id==8219423015178
    #     Eq(OurProduct.optimised.specs, None)
    # ):
    #     logger.info(f"product {prod.id} SPECS needs an optimisation")
    #     formatted_specs = "\n".join([f"{k}: {v}" for (k, v) in prod.ali.specs])
    #     # logger.debug(f"{formatted_specs=}")
    #     prod.optimised.specs = formatted_specs
        
    #     await prod.save()

    async for prod in OurProduct.find(Eq(OurProduct.optimised, None)):
        logger.info(f"product {prod.id} needs an optimisation")
        prod.optimised = OptimisedInfo(
            specs="\n".join([f"{k}: {v}" for (k, v) in prod.specs]),
            title=str(await gpt_complete(
                oai=oai,
                # model='text-curie-001',
                prompt=(
                    f"Please rewrite product title '{prod.title}' for shopify that has this"
                    "template: [Product type], [Brand], [Model], max 1-2 representative "
                    "characteristics, [Color], [Size].\n"
                    f"Product type: {prod.category}\n"
                    f"Brand: {prod.vendor}"
                    " Provide output as one line, without labels, without prefixes, without quotes. Remove repeating words."
                ),
                max_tokens=300,
                temper=0.05,  # this is to use more predictable words, more common
            )).replace(prod.vendor, "").replace(",,", ","),
            description=str(await gpt_complete(
                oai=oai,
                # model='text-curie-001',
                prompt=(
                    f"{prod.selling_points}"
                    f"{prod.specs[:20]}"
                    "\nUsing above information, write a friendly and appealing product description, "
                    "4 to 5 paragraphs, no prefixes, no quotes. Do not mention China. "
                    f"Remove vendor name {prod.vendor} from result.\n"
                ),
                max_tokens=1500,
                temper=0.1,
            )).replace(prod.vendor, ""),
        )
        await prod.save()

async def update_translations(oai: OpenAI, locale: list[str] = []) -> list[OurProduct]:
    async for prod in OurProduct.find(NE(OurProduct.optimised, None)):
        logger.debug(prod.id)
        for lang in locale:
            if not hasattr(
                    prod.translations, lang
            ) or not prod.translations.__getattribute__(lang):
                prod.translations = Translations(
                    Bulgarian=OptimisedInfo(
                        title=await text_complete(
                            oai=oai,
                            # model='text-curie-001',
                            prompt=(
                                f"translate given title into {lang} (max 60 chars): {prod.optimised.title}."
                                "Product type should go first. "
                                " Then model if specified."
                                " Measurements and attributes should follow. "
                                " Output only 1 best translation without prefixes, no quotes, "
                                "no repeat of input, no language label"
                            ),
                            max_tokens=150,
                            temper=0,
                        ),
                        description=await text_complete(
                            oai=oai,
                            # model='text-curie-001',
                            prompt=(
                                f"translate given description into {lang} (max 800 chars): {prod.optimised.description}"
                                ". Output only 1 best translation without prefixes, no quotes, no repeat of input, no language label. "
                            ),
                            max_tokens=1000,
                            temper=0.03,
                        ),
                    )
                )

        await prod.save()

    for lang in locale:
        async for prod in OurProduct.find(
                # OurProduct.shopify_id==8219423015178
                Eq(OurProduct.translations[lang].specs, None)
        ):
            logger.debug(prod.id)
            formatted_specs = "\n".join([f"{k}: {v}" for (k, v) in prod.ali.specs])
            # logger.debug(f"{formatted_specs=}")
            prod.translations.__getattribute__(lang).__setattr__(
                "specs",
                await text_complete(
                    oai=oai,
                    # model='text-curie-001',
                    prompt=(
                        f"translate given list of propery-value pairs into {lang}: {formatted_specs}."
                        "Preserve the order, do not add language label, no repeat of input. Insert line breaks (\\n) between pairs."
                        "Output only 1 best translation without prefixes."
                    ),
                    max_tokens=1300,
                    temper=0,
                ),
            )

            await prod.save()


async def main(cfg: Config):
    await dbinit()

    filtered = await filter_dirty_products(get_filters())
    # filtered = []
    await save_as_clean(filtered)
    _ = await update_titles(oai=cfg.openai)
    # _ = await update_translations(
    #     oai=cfg.openai, locale=["Bulgarian"]  # , "Polish", "Hungarian", "Bulgarian"]
    # )


if __name__ == "__main__":
    asyncio.run(main(cfg=get_config()))
