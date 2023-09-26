from beanie import Document
from pydantic import BaseModel, Field, Extra, HttpUrl, root_validator
from datetime import datetime, timedelta
from typing import Optional, Union


class Evaluation(BaseModel, extra=Extra.allow):
    starRating: float


class CategoryListing(BaseModel):
    curPageLogisticsUid: Optional[str]
    evaluation: Optional[Evaluation]
    image: dict
    itemCardType: str
    itemType: str
    lunchTime: datetime
    nativeCardType: str
    prices: dict
    productDetailUrl: Optional[str]
    productId: int
    productType: str
    sellingPoints: Union[list[dict], None]
    store: dict
    title: Optional[dict]
    trace: dict
    trade: Optional[dict]
    config: Union[dict, None]
    hasCtr: Union[bool, None]
    video: Union[dict, None]


class FeedbackRating(BaseModel):
    averageStar: float

class TitleModule(BaseModel):
    features: dict
    feedbackRating: FeedbackRating
    tradeCount: int
    orig: bool
    origTitle: bool
    subject: str

    def __init__(self, **data):

        if 'formatTradeCount' in data.keys():
            data['tradeCount'] = int(data['formatTradeCount'].strip('+').replace(',',''))
        super().__init__(**data)


class ImageModule(BaseModel):
    imagePathList: list[str]

class StoreModule(BaseModel):
    storeNum: int
    province: Optional[str]
    topRatedSeller: bool
    storeName: str
    countryCompleteName: str


class FBModule(BaseModel):
    positiveRate: str = Field(alias="sellerPositiveRate")


class QuantityModule(BaseModel):
    totalAvailQuantity: int

class BizData(BaseModel):
    shipFromCode: str
    deliveryDayMax: Optional[int] = 60
    deliveryProviderCode: Optional[str] = ''
    displayAmount: int = 0

class OriginalLayoutResult(BaseModel):
    bizData: BizData


class GeneralFreightInfo(BaseModel):
    originalLayoutResultList: list[OriginalLayoutResult]

class ShippingModule(BaseModel):
    generalFreightInfo: GeneralFreightInfo    

class DetailedListing(BaseModel):
    actionModule: Optional[dict]
    aePlusModule: Optional[dict]
    buyerProtectionModule: dict
    commonModule: dict
    # couponModule: dict
    crossLinkModule: dict
    descriptionModule: dict
    features: dict
    feedbackModule: dict
    groupShareModule: dict
    # i18nMap: dict
    imageModule: ImageModule
    installmentModule: dict
    middleBannerModule: dict
    name: str
    otherServiceModule: dict
    pageModule: dict
    preSaleModule: Optional[dict]
    prefix: str
    priceModule: dict
    quantityModule: QuantityModule
    recommendModule: dict
    redirectModule: dict
    shippingModule: ShippingModule
    skuModule: dict
    specsModule: dict
    storeModule: StoreModule
    titleModule: TitleModule
    webEnv: dict


class OriginalLayoutResultList(BaseModel):
    originalLayoutResultList: list[OriginalLayoutResult]


class WishListComponent(BaseModel):
    storeWishedCount: int


class ProductPropComponent(BaseModel):
    props: list[dict]  # attrName, attrValue



class NewDetailedListing(BaseModel):
    tradeComponent: dict
    pageSizeComponent: dict
    redirectComponent: dict
    metaDataComponent: dict
    storeFeedbackComponent: FBModule
    sellerComponent: StoreModule
    plazaSellerServiceComponent: dict
    productPropComponent: ProductPropComponent
    skuComponent: dict
    webActionConfComponent: dict
    packageComponent: dict
    productTagComponent: dict
    blacklistComponent: dict
    priceComponent: dict
    webLongImageComponent: dict
    wishListComponent: WishListComponent
    multiLanguageUrlComponent: dict
    webCouponInfoComponent: dict
    # i18nComponent: dict
    categoryComponent: dict
    buriedLogComponent: dict
    productInfoComponent: dict
    sellerGuaranteeComponent: dict
    buyerComponent: dict
    storeHeaderComponent: dict
    breadcrumbComponent: dict
    simpleBannerComponent: dict
    abTestComponent: dict
    gagaComponent: dict
    siteInfoComponent: dict
    remindsComponent: dict
    shopCategoryComponent: dict
    promotionComponent: dict
    sellerPromiseComponent: dict
    extraComponent: dict
    assuranceComponent: dict
    priceRuleComponent: dict
    webGeneralFreightCalculateComponent: OriginalLayoutResultList
    inventoryComponent: QuantityModule
    webCouponPriceComponent: dict
    installmentComponent: dict
    productDescComponent: dict
    categoryTagComponent: dict
    supplementInfoLayoutComponent: dict
    imageComponent: ImageModule
    recommendComponent: dict
    userComponent: dict
    currencyComponent: dict
    itemStatusComponent: dict
    referComponent: dict
    feedbackComponent: dict
    vehicleComponent: dict
    displayTitleComponent: dict


class AliProductIdOnly(Document):
    id: int
    added: datetime
    class Settings:
        name = "dirtyV2"

class AliProduct(Document):
    id: int
    added: datetime = Field(default_factory=datetime.utcnow)
    detailed: Optional[NewDetailedListing]
    in_category_list: Optional[CategoryListing]
    keywords: Optional[str]
    selling_points: Optional[str]
    category_query: Optional[str]
    old_import_shopify_id: Optional[int]
    old_import_shopify_barcode: Optional[int]

    class Settings:
        name = "dirtyV2"  # new
        # use_cache = True
        # cache_expiration_time = timedelta(hours=24)
        # cache_capacity = 20000

class Ean(Document):
    id: int
    prod_id: Optional[int]
    added: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "ean"
        # use_cache = True
        # cache_expiration_time = timedelta(hours=24)
        # cache_capacity = 20000

    # @root_validator
    # def ean_date_validator(cls, values):
    #     values["updated_at"] = datetime.utcnow()
    #     return values      
    
class SKU(BaseModel):
    shopify_id: Optional[int]
    id: int
    title: str
    price: float
    qty: int
    # location: str
    image: Optional[str]
    ean: Optional[int]
    shipping: float = 0


class AliInfo(BaseModel):
    title: str
    # prices: str
    images: list[str]
    vendor: Optional[str]
    description: str
    # shipped_from: str
    category: str  # strEnum?
    skus: list[SKU]
    specs: list[tuple]


    


class OptimisedInfo(BaseModel):
    title: str
    description: Optional[str]
    specs: Optional[str]


class Translations(BaseModel):
    Swedish: Optional[OptimisedInfo]
    French: Optional[OptimisedInfo]
    Dutch: Optional[OptimisedInfo]
    Bulgarian: Optional[OptimisedInfo]
    Romanian: Optional[OptimisedInfo]
    Hungarian: Optional[OptimisedInfo]
    Polish: Optional[OptimisedInfo]

class OurProductIdOnly(Document):
    id: int
    pid: int
    shopify_id: Optional[int]
    ean: Optional[int]

    class Settings:
        name = "cleanV2"

class OurProduct(Document):
    id: int
    pid: int
    shopify_id: Optional[int]
    skip: bool = False
    added: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    specs: list[tuple]  
    images: list[str]
    vendor: Optional[str]
    price: float
    qty: int
    ean: Optional[int]
    shipping: float = 0    
    description: str
    title: str
    optimised: Optional[OptimisedInfo]
    translations: Optional[Translations]
    selling_points: Optional[str]
    keywords: Optional[str]
    store: Optional[int]
    category: Optional[str]

    # type: str

    class Settings:
        name = "cleanV2"
        # use_cache = True
        # cache_expiration_time = timedelta(hours=24)
        # cache_capacity = 20000
        
    # @root_validator
    # def date_validator(cls, values):
    #     values["updated_at"] = datetime.utcnow()
    #     return values        
