#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻抓取引擎
- 基于 requests + BeautifulSoup 的启发式网页解析
- 自动检测页面类型（单篇文章 / 列表页）
- 正文提取：article 标签 → 常见正文 class → 文本密度算法
- 支持常见中文新闻网站
"""

import os
import re
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag


@dataclass
class NewsArticle:
    """新闻文章"""
    title: str = ""
    source: str = ""
    url: str = ""
    publish_date: str = ""
    author: str = ""
    content: str = ""           # 正文（纯文本）
    summary: str = ""           # 摘要
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "publish_date": self.publish_date,
            "author": self.author,
            "content_preview": self.content[:100] if self.content else "",
            "summary": self.summary,
        }


@dataclass
class ScrapeResult:
    """抓取结果"""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    articles: List[NewsArticle] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class NewsScraper:
    """新闻抓取引擎"""

    # 常见新闻正文 class/id 模式
    CONTENT_PATTERNS = [
        # class 模式
        {'type': 'class', 'patterns': [
            'article', 'content', 'maintext', 'news_text', 'article-content',
            'article_content', 'news-content', 'news_content', 'main-content',
            'main_content', 'post-content', 'post_content', 'entry-content',
            'entry_content', 'text-content', 'text_content', 'body-content',
            'detail-content', 'detail_content', 'article-body', 'article_body',
            'news-body', 'news_body', 'conText', 'con_text', 'article-main',
            'article_main', 'rich_media_content', 'richMediaContent',
        ]},
        # id 模式
        {'type': 'id', 'patterns': [
            'article', 'content', 'maintext', 'news_text', 'article-content',
            'article_content', 'news-content', 'news_content', 'main-content',
            'main_content', 'post-content', 'post_content', 'entry-content',
            'entry_content', 'text', 'detail', 'news', 'nr1',
        ]},
    ]

    # 常见站点域名（用于提取来源）
    SOURCE_MAP = {
        'people.com.cn': '人民网',
        'xinhuanet.com': '新华网',
        'news.cn': '新华网',
        'cctv.com': '央视网',
        'china.com.cn': '中国网',
        'gmw.cn': '光明网',
        'chinanews.com': '中国新闻网',
        'china daily.com': '中国日报',
        'ce.cn': '中国经济网',
        'youth.cn': '中国青年网',
        'sina.com.cn': '新浪新闻',
        'qq.com': '腾讯新闻',
        '163.com': '网易新闻',
        'sohu.com': '搜狐新闻',
        'ifeng.com': '凤凰网',
        'thepaper.cn': '澎湃新闻',
        'huanqiu.com': '环球网',
        '观察者网': '观察者网',
        'guancha.cn': '观察者网',
    }

    def __init__(self, timeout: int = 30, user_agent: str = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def scrape(self, url: str, mode: str = "auto") -> ScrapeResult:
        """
        主入口：自动检测页面类型并抓取
        :param url: 目标网址
        :param mode: "auto" 自动检测 / "single" 单篇 / "list" 列表页
        :return: ScrapeResult
        """
        mode = self._detect_page_type(url) if mode == "auto" else mode

        if mode == "single":
            article = self.scrape_single_article(url)
            if article:
                return ScrapeResult(
                    total=1, succeeded=1, articles=[article]
                )
            return ScrapeResult(total=1, failed=1, errors=["抓取失败"])

        # 列表页模式
        links = self.scrape_list_page(url)
        if not links:
            # 列表页没找到链接，尝试单篇模式
            article = self.scrape_single_article(url)
            if article:
                return ScrapeResult(
                    total=1, succeeded=1, articles=[article]
                )
            return ScrapeResult(total=1, failed=1, errors=["未找到文章链接，且单篇抓取也失败"])

        result = self.scrape_article_batch(links)
        return result

    def scrape_single_article(self, url: str) -> Optional[NewsArticle]:
        """
        抓取单篇文章
        :param url: 文章 URL
        :return: NewsArticle 或 None
        """
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')

            article = NewsArticle(url=url)

            # 提取标题
            article.title = self._extract_title(soup) or ""

            # 提取来源
            article.source = self._extract_source(soup, url)

            # 提取日期
            article.publish_date = self._extract_date(soup)

            # 提取作者
            article.author = self._extract_author(soup)

            # 提取正文
            content, summary = self._extract_content(soup)
            article.content = content
            article.summary = summary

            if not article.title and not article.content:
                return None

            return article

        except Exception as e:
            print(f"  ├─ 抓取失败 [{url[:60]}]: {e}")
            return None

    def scrape_list_page(self, url: str, max_articles: int = 20) -> List[Dict]:
        """
        抓取列表页，提取文章链接
        :param url: 列表页 URL
        :param max_articles: 最大抓取数量
        :return: [{"title": "...", "url": "..."}, ...]
        """
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(resp.text, 'lxml')

            links = []
            seen_urls = set()

            # 找所有链接
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                text = a_tag.get_text(strip=True)

                # 过滤：标题长度 8-100 字
                if len(text) < 8 or len(text) > 100:
                    continue

                # 过滤无效链接
                if href.startswith('javascript:') or href.startswith('#') or href.startswith('void'):
                    continue

                # 补全 URL
                full_url = urljoin(url, href)

                # 过滤非 http 链接
                if not full_url.startswith('http'):
                    continue

                # 去重
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                links.append({
                    "title": text,
                    "url": full_url,
                })

                if len(links) >= max_articles:
                    break

            return links

        except Exception as e:
            print(f"  ├─ 列表页抓取失败: {e}")
            return []

    def scrape_article_batch(self, article_links: List[Dict]) -> ScrapeResult:
        """
        批量抓取文章详情
        :param article_links: [{"title": "...", "url": "..."}, ...]
        :return: ScrapeResult
        """
        result = ScrapeResult(total=len(article_links))

        for i, link in enumerate(article_links):
            print(f"  ├─ 正在抓取 ({i+1}/{len(article_links)}): {link['title'][:30]}...")
            article = self.scrape_single_article(link['url'])

            if article:
                result.articles.append(article)
                result.succeeded += 1
            else:
                result.failed += 1
                result.errors.append(f"抓取失败: {link['url']}")

            # 礼貌延迟
            if i < len(article_links) - 1:
                time.sleep(0.5)

        return result

    def _detect_page_type(self, url: str) -> str:
        """检测页面类型"""
        path = urlparse(url).path.lower()

        # 单篇文章路径特征
        single_patterns = ['/article/', '/detail/', '/news/', '/a/',
                           '.html', '.shtml', '/content/', '/doc/']
        # 列表页路径特征
        list_patterns = ['/list/', '/channel/', '/index', '/page/',
                         '/roll/', '/yaowen/', '/news/roll']

        for pat in list_patterns:
            if pat in path:
                return "list"

        for pat in single_patterns:
            if pat in path:
                return "single"

        # 默认返回 list，让后续逻辑处理
        return "list"

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """提取标题"""
        # 优先 h1
        h1 = soup.find('h1')
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)

        # 其次 title 标签
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            # 清理标题中的网站名
            for sep in [' - ', ' _ ', '—', '——', '|']:
                if sep in title:
                    title = title.split(sep)[0].strip()
            if title:
                return title

        # 再找 meta
        meta_title = soup.find('meta', attrs={'property': 'og:title'})
        if meta_title and meta_title.get('content'):
            return meta_title['content'].strip()

        return None

    def _extract_source(self, soup: BeautifulSoup, url: str) -> str:
        """提取来源"""
        # 尝试 meta 标签
        for meta in soup.find_all('meta'):
            if meta.get('name', '').lower() in ('source', 'copyright', 'author'):
                content = meta.get('content', '')
                if content:
                    return content.strip()

        # 尝试 og:site_name
        meta = soup.find('meta', attrs={'property': 'og:site_name'})
        if meta and meta.get('content'):
            return meta['content'].strip()

        # 根据域名映射
        domain = urlparse(url).netloc.lower()
        for key, source_name in self.SOURCE_MAP.items():
            if key in domain:
                return source_name

        # 返回域名作为来源
        return domain.replace('www.', '').split('.')[0]

    def _extract_date(self, soup: BeautifulSoup) -> str:
        """提取发布日期"""
        # 常见日期 class/id
        date_patterns = ['date', 'time', 'pub-date', 'publish-date', 'publish_date',
                         'post-date', 'post_date', 'news-date', 'article-date',
                         'article_date', 'source_time', 'pubtime', 'createtime',
                         'release-time', 'release_time']

        for pattern in date_patterns:
            # class 匹配
            tag = soup.find(class_=re.compile(pattern, re.I))
            if tag:
                text = tag.get_text(strip=True)
                if re.search(r'\d{4}', text):
                    return text[:30]

            # id 匹配
            tag = soup.find(id=re.compile(pattern, re.I))
            if tag:
                text = tag.get_text(strip=True)
                if re.search(r'\d{4}', text):
                    return text[:30]

        # meta 标签
        for meta in soup.find_all('meta'):
            meta_name = meta.get('name', '').lower()
            meta_prop = meta.get('property', '').lower()
            if any(x in meta_name or x in meta_prop for x in ['date', 'time', 'pub', 'release']):
                content = meta.get('content', '')
                if re.search(r'\d{4}', content):
                    return content[:30]

        return ""

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """提取作者"""
        author_patterns = ['author', 'writer', 'editor', 'byline', 'contributor']

        for pattern in author_patterns:
            tag = soup.find(class_=re.compile(pattern, re.I))
            if tag:
                text = tag.get_text(strip=True)
                text = re.sub(r'^(作者|责编|责任编辑|编辑|记者)[：:]\s*', '', text)
                if text and len(text) < 20:
                    return text

            tag = soup.find(id=re.compile(pattern, re.I))
            if tag:
                text = tag.get_text(strip=True)
                text = re.sub(r'^(作者|责编|责任编辑|编辑|记者)[：:]\s*', '', text)
                if text and len(text) < 20:
                    return text

        # meta
        meta = soup.find('meta', attrs={'name': 'author'})
        if meta and meta.get('content'):
            return meta['content'].strip()

        return ""

    def _extract_content(self, soup: BeautifulSoup) -> Tuple[str, str]:
        """
        提取正文内容
        :return: (正文纯文本, 摘要)
        """
        # 1. 按优先级查找正文容器
        content_tag = self._find_content_container(soup)

        if content_tag:
            # 清理干扰元素
            self._remove_noise(content_tag)
            text = content_tag.get_text('\n', strip=True)
        else:
            # 2. 回退：文本密度算法
            text = self._extract_by_text_density(soup)

        # 清理文本
        text = self._clean_content_text(text)

        # 生成摘要
        summary = text[:150] if len(text) > 150 else text

        return text, summary

    def _find_content_container(self, soup: BeautifulSoup) -> Optional[Tag]:
        """按优先级查找正文容器"""
        # 1. article 标签
        article_tag = soup.find('article')
        if article_tag:
            text_len = len(article_tag.get_text(strip=True))
            if text_len > 300:
                return article_tag

        # 2. class 模式
        for pattern_group in self.CONTENT_PATTERNS:
            for pattern in pattern_group['patterns']:
                if pattern_group['type'] == 'class':
                    tag = soup.find(class_=re.compile(pattern, re.I))
                else:
                    tag = soup.find(id=re.compile(pattern, re.I))

                if tag:
                    text_len = len(tag.get_text(strip=True))
                    if text_len > 300:
                        return tag

        return None

    def _remove_noise(self, tag: Tag):
        """移除干扰元素"""
        selectors = [
            'script', 'style', 'nav', 'header', 'footer', 'aside',
            '.ad', '.ads', '.advertisement', '.banner', '.side',
            '.sidebar', '.comment', '.comments', '.share', '.recommend',
            '.related', '.footer', '.header', '.nav', '.topbar',
            '#ad', '#ads', '#side', '#sidebar', '#comment', '#footer',
        ]
        for selector in selectors:
            for elem in tag.select(selector):
                elem.decompose()

    def _clean_content_text(self, text: str) -> str:
        """清理正文文本"""
        # 移除多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 移除多余空格
        text = re.sub(r' {2,}', ' ', text)
        # 移除纯数字/符号行
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            line = line.strip()
            if not line:
                cleaned.append('')
                continue
            # 跳过广告特征行
            if re.match(r'^[\d\s《》【】\[\]\(\)（）\-—_]+$', line):
                continue
            cleaned.append(line)

        return '\n'.join(cleaned).strip()

    def _extract_by_text_density(self, soup: BeautifulSoup) -> str:
        """
        文本密度算法提取正文
        计算每个块级元素的文本密度，选择密度最高的连续区域
        """
        # 移除干扰元素
        self._remove_noise(soup)

        # 找正文区域（body 内）
        body = soup.find('body') or soup
        divs = body.find_all(['div', 'section', 'article', 'main'])

        best_div = None
        best_density = 0

        for div in divs:
            text = div.get_text(strip=True)
            if len(text) < 200:
                continue

            # 计算文本密度：文本长度 / HTML 长度
            html_len = len(str(div))
            if html_len == 0:
                continue

            density = len(text) / html_len

            if density > best_density:
                best_density = density
                best_div = div

        if best_div:
            return best_div.get_text('\n', strip=True)

        # 最终回退
        return body.get_text('\n', strip=True)[:5000]
