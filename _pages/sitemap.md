---
layout: archive
title: "Sitemap"
permalink: /sitemap/
author_profile: true
---

{% include base_path %}

All pages on this site, in English and in Japanese, followed by the publication records. An [XML sitemap]({{ base_path }}/sitemap.xml) is also available.

## English pages

{% assign _pages_en = site.pages | where: "lang", "en" | sort: "title" %}
<ul>
{% for p in _pages_en %}
  <li><a href="{{ base_path }}{{ p.url }}">{{ p.title }}</a></li>
{% endfor %}
</ul>

## 日本語ページ

{% assign _pages_ja = site.pages | where: "lang", "ja" | sort: "title" %}
<ul>
{% for p in _pages_ja %}
  <li><a href="{{ base_path }}{{ p.url }}">{{ p.title }}</a></li>
{% endfor %}
</ul>

{% if site.publications.size > 0 %}
## Publications

{% assign _pubs = site.publications | sort: "date" | reverse %}
<ol class="publication-list">
{% for post in _pubs %}
  {% include publication-entry.html pub_index=forloop.index %}
{% endfor %}
</ol>
{% endif %}
