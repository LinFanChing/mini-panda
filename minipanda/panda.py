# -*- coding: utf-8 -*-
import os
import codecs
import json
import re
import ntpath
import shutil
import sys
import urllib2
from jinja2 import FileSystemLoader, Environment
from time import strptime, strftime
from fnmatch import fnmatch
from markdown import markdown


def string2bool(string):
    return string.strip() in ['true', 'True', 't', 'T']


def string2datetime(string):
    return strptime(string, '%Y-%m-%d %H:%M')


def seperate_name_and_slug(string):
    item = dict()
    result = re.search('(.*?)\{(.*?)\}', string)
    if result:
        item['slug'] = result.group(2).strip()
        item['name'] = result.group(1).strip()
    else:
        item['slug'] = urllib2.quote(string.encode('utf8'))
        item['name'] = string
    return item


def resolve_slug_conflict(items):
    items.sort(key=lambda x: x['date'])
    slugs = {'date', 'tag', 'author', 'category'}
    for item in items:
        no = 1
        slug = item['slug']
        while slug in slugs:
            slug = item['slug'] + '-' + str(no)
            no += 1
        item['slug'] = slug
        slugs.add(slug)


def load_item_from_file(item, config):
    accepting_meta = [
        'title', 'slug', 'date', 'tags', 'category', 'draft', 'page', 'author', 'type']
    with codecs.open(item['file'], 'r', encoding='utf-8') as fp:
        item['title'] = ntpath.basename(item['file'])[:-3]
        item['slug'] = urllib2.quote(item['title'])
        item['date'] = '2000-01-01 00:00'
        item['category'] = 'uncategorized'
        item['type'] = 'post'
        item['summary'] = ''
        item['tags'] = []
        item['author'] = config['default_author']
        item['md_content'] = ''
        setting_meta = True
        for line in fp.read().splitlines():
            if line == '':
                setting_meta = False
                continue
            if setting_meta:
                result = re.search('^(.*?):(.*?)$', line, re.IGNORECASE)
                if result:
                    attr, value = result.group(1).strip().lower(), result.group(2).strip()
                    if attr in accepting_meta:
                        item[attr] = value
            else:
                item['md_content'] += line + '\n'
        item['tags'] = [tag.strip() for tag in item['tags'].split(',')]
        item['date'] = string2datetime(item['date'])
        item['tags'] = map(seperate_name_and_slug, item['tags'])
        item['category'] = seperate_name_and_slug(item['category'])
        item['author'] = seperate_name_and_slug(item['author'])
        item['type'] = item['type'].lower()
        if not item['type'] in ['post', 'page', 'draft']:
            item['type'] = 'post'
        item['content'] = markdown(item['md_content'])


def load_source(config):
    source_path = os.path.join(config['site_path'], 'src')
    items = list()
    for folder_path, folder_names, files in os.walk(source_path):
        for md_file in files:
            filename = os.path.join(folder_path, md_file)
            if fnmatch(filename, '*.md'):
                items.append(dict(file=filename))
    map(lambda item: load_item_from_file(item, config), items)
    resolve_slug_conflict(items)
    return items


def create_archives(items, config):
    archives = dict()

    def add_post(archive_type, slug, name, post):
        if config['archive_enable'][archive_type]:
            if not (archive_type, slug) in archives:
                archives[(archive_type, slug)] = {'name': name, 'posts': []}
            archives[(archive_type, slug)]['posts'].append(post)

    for item in filter(lambda x: x['type'] == 'post', items):
        add_post('category', item['category']['slug'], item['category']['name'], item)
        add_post('author', item['author']['slug'], item['author']['name'], item)
        for tag in item['tags']:
            add_post('tag', tag['slug'], tag['name'], item)
        date_string = strftime('%Y-%m', item['date'])
        assert date_string
        add_post('date', date_string, date_string, item)

    titles = {
        'date': u'Archive of {name}',
        'author': u'Posts Written by {name}',
        'category': u'Posts in the category {name}',
        'tag': u'Posts with the tag {name}'
    }
    archive_list = []
    for key, value in archives.iteritems():
        archive_list.append({
            'title': titles[key[0]].format(name=value['name']),
            'type': key[0],
            'slug': key[1],
            'posts': value['posts']
        })
    return archive_list


def generate_output(item, config):
    templates = config['templates']
    assert config
    if item['type'] == 'post':
        item['output'] = templates['post'].render(item=item, config=config)
        item['output_path'] = os.path.join(config['output_path'], item['slug'])
    elif item['type'] == 'page':
        item['output'] = templates['page'].render(item=item, config=config)
        item['output_path'] = os.path.join(config['output_path'], item['slug'])
    elif item['type'] in ['tag', 'author', 'date', 'category']:
        item['output'] = templates['archive'].render(item=item, config=config)
        item['output_path'] = os.path.join(config['output_path'], item['type'], item['slug'])


def write_output(item, config):
    if 'output_path' in item:
        os.mkdir(item['output_path'])
        with codecs.open(os.path.join(item['output_path'], 'index.html'),
                         'w', encoding='utf8') as fp:
            fp.write(item['output'])


def publish(items, config):
    if os.path.isfile(config['output_path']):
        os.remove(config['output_path'])
    elif os.path.isdir(config['output_path']):
        shutil.rmtree(config['output_path'])
    paths = ['', 'date', 'tag', 'author', 'category']
    for path in paths:
        os.mkdir(os.path.join(config['output_path'], path))
    for item in items:
        write_output(item, config)


def init(site_path):
    config_file = os.path.join(site_path, 'config.json')
    with codecs.open(config_file, 'r', encoding='utf-8') as fp:
        config = json.load(fp)
    config['site_path'] = site_path
    config['output_path'] = os.path.join(site_path, 'output')
    config['env'] = Environment(
        loader=FileSystemLoader(os.path.join(site_path, 'template')))
    config['templates'] = {
        'index': config['env'].get_template('index.html'),
        'post': config['env'].get_template('post.html'),
        'page': config['env'].get_template('page.html'),
        'archive': config['env'].get_template('archive.html')
    }
    return config


def run(site_path):
    config = init(site_path)
    items = load_source(config)
    items += create_archives(items, config)
    map(lambda x: generate_output(x, config), items)
    publish(items, config)
    assert items

if __name__ == '__main__':
    run(sys.argv[1])