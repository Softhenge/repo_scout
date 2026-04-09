from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class GitHubUser(BaseModel):
    login: str
    id: int
    avatar_url: Optional[str] = None
    html_url: Optional[str] = None
    type: Optional[str] = None


class GitHubLicense(BaseModel):
    key: Optional[str] = None
    name: Optional[str] = None
    spdx_id: Optional[str] = None


class GitHubRepo(BaseModel):
    id: int
    name: str
    full_name: str
    owner: GitHubUser
    description: Optional[str] = None
    html_url: str
    clone_url: Optional[str] = None
    language: Optional[str] = None
    stargazers_count: int = 0
    watchers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    topics: list[str] = Field(default_factory=list)
    is_private: bool = Field(alias="private", default=False)
    archived: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None
    size: int = 0
    default_branch: str = "main"
    license: Optional[GitHubLicense] = None

    model_config = {"populate_by_name": True}


class SearchResult(BaseModel):
    total_count: int
    incomplete_results: bool
    items: list[GitHubRepo]


class ContributorInfo(BaseModel):
    login: str
    id: int
    avatar_url: Optional[str] = None
    html_url: Optional[str] = None
    contributions: int = 0
    type: Optional[str] = None


class GitHubIssue(BaseModel):
    id: int
    number: int
    title: str
    state: str
    html_url: str
    user: Optional[GitHubUser] = None
    labels: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    comments: int = 0
    body: Optional[str] = None
