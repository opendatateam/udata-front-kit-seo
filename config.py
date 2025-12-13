import os

from dataclasses import dataclass
from enum import StrEnum

import dacite
import requests
import yaml


class DeployEnv(StrEnum):
    PROD = 'prod'
    PREPROD = 'preprod'
    DEMO = 'demo'


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
class WebsiteConfig:
    seo: SeoConfig

@dataclass
class Config:
    website: WebsiteConfig
    datagouvfr: DatagouvfrConfig
    pages: dict[str, PageConfig]


def parse_config() -> Config:
    deploy_env = DeployEnv(os.getenv("ENV"))
    print(f"-> env: {deploy_env.value!r}")

    site = os.getenv("SITE")

    if not site:
        raise ValueError("SITE env var not set.")

    gh_branch = f"{site}-{deploy_env}"
    gh_url = f"https://raw.githubusercontent.com/opendatateam/udata-front-kit/refs/heads/{gh_branch}/configs/{site}/config.yaml"
    # FIXME: test commit
    gh_url = "https://raw.githubusercontent.com/opendatateam/udata-front-kit/f453959f0c8e44804bd65e90b6f3fc342d3962dd/configs/ecospheres/config.yaml"

    r = requests.get(gh_url)
    if not r.ok:
        raise ValueError(f"Could not fetch config from {gh_url}")

    config_dict = yaml.safe_load(r.text)
    config = dacite.from_dict(Config, config_dict)

    print(f"-> site: {site!r}")
    print(f"-> config url: {gh_url!r}")
    print(f"-> seo config:\n{yaml.dump(config_dict["website"]["seo"], default_flow_style=False, indent=2)}")

    return config
