from __future__ import annotations

from .base import (
    Job,
    BaseScraper,
    USER_AGENTS,
    NON_JOB_DOMAINS,
    PRE_FILTER_DISQUALIFIERS,
    NOISE_COMPANY_PATTERNS,
    COMPANY_STRIP_SUFFIXES,
    get_random_headers,
    get_session,
    is_valid_job_offer,
    clean_job_description,
    clean_company_name,
    normalize_company_name,
    normalize_title_name,
    get_job_dedup_key,
    normalize_title_company_for_hash,
)
from .linkedin import LinkedInScraper
from .itjobs import ITJobsScraper
from .landingjobs import LandingJobsScraper
from .remotive import RemotiveScraper
from .arbeitnow import ArbeitnowScraper
from .remoteok import RemoteOKScraper
from .cargadetrabalhos import CargaDeTrabalhosScraper
from .jobicy import JobicyScraper
from .netempregos import NetEmpregosScraper
from .jobspresso import JobspressoScraper
from .euraxess import EuraxessScraper
from .iefp import IEFPScraper
from .indeed import IndeedScraper
from .sapo import SapoScraper
from .teamlyzer import TeamlyzerScraper
from .pipeline import JobIngestionPipeline

__all__ = [
    "Job",
    "BaseScraper",
    "USER_AGENTS",
    "NON_JOB_DOMAINS",
    "PRE_FILTER_DISQUALIFIERS",
    "NOISE_COMPANY_PATTERNS",
    "COMPANY_STRIP_SUFFIXES",
    "get_random_headers",
    "get_session",
    "is_valid_job_offer",
    "clean_job_description",
    "clean_company_name",
    "normalize_company_name",
    "normalize_title_name",
    "get_job_dedup_key",
    "normalize_title_company_for_hash",
    "LinkedInScraper",
    "ITJobsScraper",
    "IndeedScraper",
    "LandingJobsScraper",
    "RemotiveScraper",
    "ArbeitnowScraper",
    "RemoteOKScraper",
    "CargaDeTrabalhosScraper",
    "JobicyScraper",
    "NetEmpregosScraper",
    "JobspressoScraper",
    "EuraxessScraper",
    "IEFPScraper",
    "SapoScraper",
    "TeamlyzerScraper",
    "JobIngestionPipeline",
]
