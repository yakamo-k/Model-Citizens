#!/usr/bin/env python3
"""Build a static reader from main. Repository content is never executed.

python3 -m pip install -r tools/requirements-reader.txt
python3 tools/build_reader.py --output /path/to/new-site
Use --source . to preview uncommitted Markdown locally instead of cloning.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt

REPO = "https://github.com/yakamo-k/Model-Citizens"
GROUPS = ("docs", "proposals", "critiques", "experiments", "decisions", "templates")
PRIORITY = ["README.md", "docs/SHARED-GOAL.md", "docs/HUMAN-NATURE.md",
            "docs/MORAL-COMMONS.md", "docs/SCIENTIFIC-STANDARDS.md",
            "docs/FOUNDATIONS.md", "docs/OPEN-QUESTIONS.md", "CONTRIBUTING.md"]
LABELS = {"README.md": "Overview", "docs/SHARED-GOAL.md": "Shared goal",
          "docs/HUMAN-NATURE.md": "Human nature", "docs/MORAL-COMMONS.md": "Moral Commons",
          "docs/SCIENTIFIC-STANDARDS.md": "Scientific standards", "docs/FOUNDATIONS.md": "Foundations",
          "docs/OPEN-QUESTIONS.md": "Open questions", "CONTRIBUTING.md": "How to contribute"}
ESC = html.escape


def git(*args, cwd=None):
    return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd, text=True).strip()


def allowed(name):
    path = PurePosixPath(name)
    return name in {"README.md", "CONTRIBUTING.md"} or (
        path.parts[0] in GROUPS and path.suffix.lower() == ".md" and
        not any(part.startswith(".") for part in path.parts))


def slug(text):
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def destination(name):
    return "index.html" if name == "README.md" else str(PurePosixPath(name).with_suffix(".html"))


class Checker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links = set(), []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        if tag in {"script", "link"}:
            resource = attrs.get("src") or attrs.get("href")
            if resource:
                self.links.append(resource)


def validate(folder):
    parsed = {}
    for path in folder.rglob("*.html"):
        checker = Checker()
        checker.feed(path.read_text())
        parsed[path.relative_to(folder).as_posix()] = checker
    for name, checker in parsed.items():
        for href in checker.links:
            url = urlsplit(href)
            if url.scheme or url.netloc:
                continue
            target = unquote(url.path).lstrip("/") if url.path.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
            if not url.path:
                target = name
            if not (folder / target).is_file():
                raise ValueError(f"Broken link: {name} -> {href}")
            if url.fragment and target in parsed and unquote(url.fragment) not in parsed[target].ids:
                raise ValueError(f"Broken heading link: {name} -> {href}")


def build(source, output, revision):
    if output.exists():
        raise ValueError("Output must be a new directory; existing sites are never overwritten.")
    docs = {}
    for path in source.rglob("*.md"):
        name = path.relative_to(source).as_posix()
        if allowed(name):
            if path.is_symlink() or source.resolve() not in path.resolve().parents:
                raise ValueError(f"Unsupported document path: {name}")
            if path.stat().st_size > 2_000_000:
                raise ValueError(f"Document too large: {name}")
            docs[name] = path.read_text(encoding="utf-8")
    if not all(name in docs for name in PRIORITY):
        raise ValueError("Missing required seed documents.")
    if sum(len(text) for text in docs.values()) > 20_000_000:
        raise ValueError("Document collection exceeds build size limit.")
    order = [*PRIORITY, *sorted(set(docs) - set(PRIORITY))]
    titles = {name: (re.search(r"^#\s+(.+)$", text, re.M).group(1) if re.search(r"^#\s+(.+)$", text, re.M) else PurePosixPath(name).stem.replace("-", " ").title()) for name, text in docs.items()}
    routes = {name: destination(name) for name in docs}
    routes.update({group: group + "/index.html" for group in GROUPS})
    parser = MarkdownIt("js-default").disable("image")
    bodies, contents = {}, {}
    for name, text in docs.items():
        tokens = parser.parse(text)
        anchors, seen = [], {}
        for index, token in enumerate(tokens):
            if token.type == "heading_open":
                title = tokens[index + 1].content
                base = slug(title)
                number = seen.get(base, 0)
                seen[base] = number + 1
                ident = "h-" + base + (f"-{number}" if number else "")
                token.attrSet("id", ident)
                if token.tag in {"h2", "h3"}:
                    anchors.append((ident, title, token.tag))
            for child in token.children or []:
                if child.type != "link_open":
                    continue
                href = child.attrGet("href") or ""
                url = urlsplit(href)
                if url.scheme or url.netloc:
                    child.attrSet("rel", "noreferrer")
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path))) if url.path else name
                route = routes.get(target.rstrip("/"))
                if route:
                    fragment = "#h-" + quote(unquote(url.fragment)) if url.fragment else ""
                    child.attrSet("href", "/" + quote(route) + fragment)
                elif url.path.endswith(".md"):
                    raise ValueError(f"Unresolved Markdown link: {name} -> {href}")
                else:
                    child.attrSet("href", REPO + "/blob/main/" + quote(target))
        bodies[name] = parser.renderer.render(tokens, parser.options, {})
        contents[name] = anchors
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reader-build-", dir=output.parent) as staging:
        stage = Path(staging) / "site"
        assets = stage / "assets"
        assets.mkdir(parents=True)
        trusted_assets = Path(__file__).resolve().parent / "reader-assets"
        for asset in ("reader.css", "reader.js"):
            shutil.copyfile(trusted_assets / asset, assets / asset)

        def navigation(current):
            links = '<div class="nav-label">The framework</div>'
            for name in PRIORITY:
                if name == "CONTRIBUTING.md":
                    continue
                active = ' aria-current="page"' if name == current else ""
                links += f'<a href="/{routes[name]}"{active}>{ESC(LABELS.get(name, titles[name]))}</a>'
            links += '<div class="nav-label">Explore &amp; contribute</div>'
            for group in GROUPS[1:]:
                active = ' aria-current="page"' if current == group else ""
                links += f'<a href="/{group}/index.html"{active}>{group.title()}</a>'
            links += '<a href="/CONTRIBUTING.html">How to contribute</a>'
            extra = [n for n in order if n not in PRIORITY and n.startswith("docs/")]
            if extra:
                links += '<div class="nav-label">Further reading</div>'
                links += "".join(f'<a href="/{routes[n]}">{ESC(titles[n])}</a>' for n in extra)
            return links

        def page(name, title, body, toc=(), source_name=None):
            toc_html = "".join(f'<a class="{level}" href="#{ESC(ident)}">{ESC(label)}</a>' for ident, label, level in toc)
            source_url = REPO + ("/edit/main/" + quote(source_name) if source_name else "/issues/new")
            source_label = "Edit on GitHub ↗" if source_name else "Propose on GitHub ↗"
            revision_url = REPO + "/commit/" + revision if re.fullmatch(r"[0-9a-f]{40}", revision) else REPO
            footer = ""
            if source_name in order:
                index = order.index(source_name)
                for offset, label in ((-1, "Previous"), (1, "Next")):
                    next_index = index + offset
                    if 0 <= next_index < len(order):
                        other = order[next_index]
                        footer += f'<a href="/{routes[other]}"><small>{label}</small>{ESC(LABELS.get(other, titles[other]))} {"←" if offset < 0 else "→"}</a>'
            return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Explore Model Citizens: human nature, an open moral framework, and better governance.">
<title>{ESC(title)} · Model Citizens</title><link rel="stylesheet" href="/assets/reader.css"><script src="/assets/reader.js" defer></script></head>
<body><a class="skip" href="#reading">Skip to content</a>
<header class="topbar"><a class="brand" href="/index.html">unrelated<span>.</span> <span class="brand-divider">/</span> <span class="project-name">Model Citizens</span></a><a class="repository" href="{REPO}" rel="noreferrer">Contribute on GitHub ↗</a><button id="menu-toggle" aria-expanded="false" aria-controls="sidebar">Menu</button></header>
<div class="layout"><aside class="sidebar" id="sidebar"><label class="search-label" for="search">Search the framework</label><input type="search" id="search" placeholder="Search ideas…" autocomplete="off"><div id="search-results" aria-live="polite"></div><nav aria-label="Document navigation">{navigation(name)}</nav><div class="sidebar-note">An open framework.<br>Every claim is open to criticism.</div></aside>
<main id="reading"><div class="page-meta"><span class="draft">Seed draft · open to revision</span><a href="{source_url}" rel="noreferrer">{source_label}</a></div><article>{body}</article>
<div class="contribute"><h2>Help improve this thinking.</h2><p>Read here. Discuss, suggest edits, and submit pull requests on GitHub. These documents are a starting point, not a finished system.</p><a href="{source_url}" rel="noreferrer">{source_label}</a><a href="{REPO}/issues" rel="noreferrer">Discuss an idea ↗</a></div>
<nav class="page-turn" aria-label="Continue reading">{footer}</nav><footer>Published from <a href="{revision_url}" rel="noreferrer">revision {ESC(revision[:7])}</a> · {datetime.now(timezone.utc).strftime('%d %b %Y')} UTC</footer></main>
<aside class="toc"><div class="nav-label">On this page</div><nav aria-label="On this page">{toc_html or '<span>Browse this collection</span>'}</nav></aside></div></body></html>'''

        for name in order:
            path = stage / routes[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page(name, titles[name], bodies[name], contents[name], name))
        for group in GROUPS:
            members = [name for name in order if name.startswith(group + "/")]
            cards = "".join(f'<a class="collection-item" href="/{routes[name]}"><span>{ESC(titles[name])}</span><span aria-hidden="true">→</span></a>' for name in members)
            if not members:
                cards = '<p class="empty">No documents here yet. This space is ready for contributions. Start with a proposal or critique template, then open a pull request.</p><p><a href="/templates/index.html">Explore contribution templates →</a></p>'
            body = f'<h1>{group.title()}</h1><p class="collection-intro">Explore the {group} being developed as part of Model Citizens.</p><div class="collection">{cards}</div>'
            (stage / group).mkdir(exist_ok=True)
            (stage / group / "index.html").write_text(page(group, group.title(), body))
        search = [{"title": LABELS.get(name, titles[name]), "url": "/" + routes[name], "text": re.sub(r"\s+", " ", docs[name])} for name in order]
        (assets / "search.json").write_text(json.dumps(search, ensure_ascii=False))
        (stage / "build.json").write_text(json.dumps({"repository": REPO, "revision": revision, "documents": len(docs)}))
        validate(stage)
        stage.rename(output)
    print(f"Built {len(docs)} documents and {len(GROUPS)} collection pages from {revision[:7]} into {output}")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, help="Local document checkout (omit to pull public main)")
    cli.add_argument("--output", required=True, type=Path, help="New output directory")
    args = cli.parse_args()
    if args.source:
        source = args.source.resolve()
        revision = git("rev-parse", "HEAD", cwd=source)
        build(source, args.output.resolve(), revision)
    else:
        with tempfile.TemporaryDirectory(prefix="model-citizens-source-") as temp:
            checkout = Path(temp) / "repo"
            git("clone", "--depth", "1", "--single-branch", "--branch", "main", "--no-checkout", REPO + ".git", str(checkout))
            revision = git("rev-parse", "HEAD", cwd=checkout)
            docs = Path(temp) / "documents"
            docs.mkdir()
            # Read document blobs directly; do not check out or run repository code.
            for entry in git("ls-tree", "-rz", "HEAD", cwd=checkout).split("\0"):
                if not entry:
                    continue
                metadata, name = entry.split("\t", 1)
                mode, kind, blob = metadata.split()
                if not allowed(name):
                    continue
                if mode not in {"100644", "100755"} or kind != "blob":
                    raise ValueError(f"Unsupported document type: {name}")
                size = int(git("cat-file", "-s", blob, cwd=checkout))
                if size > 2_000_000:
                    raise ValueError(f"Document too large: {name}")
                path = docs / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(git("cat-file", "blob", blob, cwd=checkout) + "\n")
            build(docs, args.output.resolve(), revision)


if __name__ == "__main__":
    main()
