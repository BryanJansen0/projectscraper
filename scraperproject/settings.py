from pydantic import BaseSettings

removables = r"(aliexpress|china|us plug|110v|fahrenheit)[\s]*"


class Shopify(BaseSettings):
    key: str = "43fb5252bba11b9717ff2acc137e4b9d"
    secret: str = "cd416baaa9cda6d7c70490189a387be5"
    shpat: str = "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"



class OpenAI(BaseSettings):
    key: str = "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"
    org: str = "org-jup4KaiPQ9zpxUgUQDaUjsWI"


class Config(BaseSettings):
    video: dict = {"width": 800, "height": 600}
    timeout: int = 60000
    ali_dutch_usd_cookies: dict = {
        "name": "aep_usuc_f",
        "value": "site=glo&c_tp=USD&region=NL&b_locale=en_US",
        "domain": ".aliexpress.com",
        "path": "/",
    }
    ali_romanian_usd_cookies: dict = {
        "name": "aep_usuc_f",
        "value": "site=glo&c_tp=USD&region=RO&b_locale=en_US",
        "domain": ".aliexpress.com",
        "path": "/",
    }    
    dida: str = "window._dida_config_._init_data_"
    openai: OpenAI = OpenAI()
    shopify: Shopify = Shopify()


class Filters(BaseSettings):
    min_prod_rating: float = 4.5  # dirty
    min_orders: int = 1 # 5
    min_stock: int = 3
    max_stock: int = 10000
    min_store_rating: float = 85  # %
    min_store_followers: int = 500
    max_delivery: int = 14
    shipping_from: list[str] = ["PL", "DE", "FR", "ES", "IT", "CZ", "BE", "NL", "TR"]
    shipping_from_avoid: list[str] = ["CN", "US", "RU", "CA", "UK", "AE"]
    min_price: float = 35  # dirty
    max_price: float = 450  # dirty
    plus_only: bool = False  # dirty
    top_rated_seller: bool = False


def get_config():
    return Config()


def get_filters():
    return Filters()
