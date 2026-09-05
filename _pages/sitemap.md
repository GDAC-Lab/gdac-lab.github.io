---
layout: archive
title: "Sitemap"
permalink: /sitemap/
author_profile: true
---

{% include base_path %}

A list of all the pages found on the site. For you robots out there, there is an [XML version]({{ base_path }}/sitemap.xml) available for digesting as well.

<h2>Pages</h2>
{% for post in site.pages %}
  {% include archive-single.html %}
{% endfor %}

{% if site.posts.size > 0 %}
<h2>Posts</h2>
{% for post in site.posts %}
  {% include archive-single.html %}
{% endfor %}
{% endif %}

{% comment %}
Collections are listed only when they actually hold documents, so the empty
collections this site keeps configured (talks, teaching, portfolio) do not
render bare headings here.
{% endcomment %}
{% for collection in site.collections %}
{% unless collection.output == false or collection.label == "posts" or collection.docs.size == 0 %}
  <h2>{{ collection.label }}</h2>
  {% for post in collection.docs %}
    {% include archive-single.html %}
  {% endfor %}
{% endunless %}
{% endfor %}
