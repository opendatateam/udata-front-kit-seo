import os

from dataclasses import asdict, dataclass
from enum import StrEnum

import dacite
import requests
import yaml


class DeployEnv(StrEnum):
    PROD = "prod"
    PREPROD = "preprod"
    DEMO = "demo"


@dataclass
class MetaConfig:
    keywords: str | None = None
    description: str | None = None
    robots: str | None = None

@dataclass
class RobotsTxtConfig:
    disallow: list[str] | None = None

@dataclass
class SitemapXmlConfig:
    topics_pages: list[str] | None = None
    datasets_pages: list[str] | None = None
    dataservices_pages: list[str] | None = None
    static_urls: list[str] | None = None

@dataclass
class SeoConfig:
    canonical_url: str
    meta: MetaConfig | None = None
    sitemap_xml: SitemapXmlConfig | None = None
    robots_txt: RobotsTxtConfig | None = None

@dataclass
class PageConfig:
    universe_query: dict

@dataclass
class DatagouvfrConfig:
    base_url: str

@dataclass
class StaticPageConfig:
    title: str
    id: str
    route: str
    url: str

@dataclass
class RouterConfig:
    static_pages: list[StaticPageConfig] | None

@dataclass
class WebsiteConfig:
    seo: SeoConfig
    router: RouterConfig

@dataclass
class Config:
    website: WebsiteConfig
    datagouvfr: DatagouvfrConfig
    pages: dict[str, PageConfig]


def parse_config() -> tuple[Config, str]:
    deploy_env = DeployEnv(os.getenv("ENV"))
    print(f"-> env: {deploy_env.value!r}")

    site = os.getenv("SITE")
    if not site:
        raise ValueError("SITE env var not set.")
    print(f"-> site: {site!r}")

    # map ecologie to ecospheres if needed
    gh_site = site if site != "ecologie" else "ecospheres"
    print(f"-> gh_site: {gh_site!r}")

    gh_branch = f"{gh_site}-{deploy_env}"
    gh_url = f"https://raw.githubusercontent.com/opendatateam/udata-front-kit/refs/heads/{gh_branch}/configs/{gh_site}/config.yaml"
    print(f"-> config url: {gh_url!r}")

    try:
        r = requests.get(gh_url)
        r.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"Could not fetch config from {gh_url}: {e}")

    config_dict = yaml.safe_load(r.text)
    config = dacite.from_dict(Config, config_dict)

    print(f"-> seo config:\n{yaml.dump(asdict(config.website.seo), default_flow_style=False, indent=2)}")

    # config object, site/env path like ecologie/prod
    return config, f"{site}/{deploy_env.value}"
