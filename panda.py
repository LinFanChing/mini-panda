# -*- coding: utf-8 -*-
import os
from os.path import join as join_path
from codecs import open
# import json
import re
from ntpath import basename
import shutil
import sys
import urllib2
from jinja2 import FileSystemLoader, Environment
from time import strptime, strftime
from fnmatch import fnmatch
from markdown import markdown

config = {
    'title': 'My Foobar Blog',
    'description': 'This is just a simple foobar blog',
    'url': 'http://localhost'
}


class Tag(object):
    def __init__(self, tag_str):
        self.name = self.slug = tag_str.strip()
        result = re.search('(.*?)\{(.*?)\}', tag_str)
        if result:
            self.slug = urllib2.quote(result.group(2).strip().encode('utf8'))
            self.name = result.group(1).strip()

    def __hash__(self):
        return hash(self.slug)

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()


class Post(object):
    def __init__(self, src_file):
        self.slug = self.title = basename(src_file)
        self.date = strptime('2000-01-01 12:00', '%Y-%m-%d %H:%M')
        self.archive = '2000-01'
        self.tags = []
        self.content = ''
        self._load_from_file(src_file)
        self.pre_post = self.next_post = None

    def _load_from_file(self, src_file):
        fp = open(src_file, 'r', encoding='utf-8')
        lines = fp.read().splitlines()
        set_meta = True
        for line in lines:
            if set_meta:
                result = re.search('^(.*?):(.*?)$', line)
                if result:
                    meta = result.group(1).strip().lower()
                    value = result.group(2).strip()
                    self._set_meta(meta, value)
                if line == u'':
                    set_meta = False
                    continue
            else:
                self.content += line + '\n'
        self.content = markdown(self.content)

    def _set_meta(self, meta, value):
        if meta == 'title' or meta == 'slug':
            setattr(self, meta, value)
        elif meta == 'tags':
            self.tags = [Tag(tag_str) for tag_str in value.split(',')]
        elif meta == 'date':
            self.date = strptime(value, '%Y-%m-%d %H:%M')
            self.archive = strftime('%Y-%m', self.date)

    def __le__(self, other):
        return self.date < other.date


class Blog(object):
    def __init__(self, blog_path, config):
        self.src_path = join_path(blog_path, 'src')
        self.output_path = join_path(blog_path, 'output')
        self.template_path = join_path(blog_path, 'template')
        self.posts = []
        for name, value in config.iteritems():
            setattr(self, name, value)

    def _add_post(self, post):
        self.posts.append(post)

    def _resolve_slug_conflicts(self):
        self.posts = sorted(self.posts, key=lambda x: x.date)
        used_slugs = {'archive', 'tag'}
        for post in self.posts:
            no = 1
            slug = post.slug
            while slug in used_slugs:
                slug = post.slug + '-' + str(no)
                no += 1
            post.slug = slug
            used_slugs.add(slug)

    def _load(self):
        for folder_path, folder_names, files in os.walk(self.src_path):
            for src_file in files:
                filename = join_path(folder_path, src_file)
                if fnmatch(filename, '*.md'):
                    self._add_post(Post(filename))
        self._resolve_slug_conflicts()
        self._set_pre_and_next_post()
        self.archives = self._generate_archives()
        self.tags = self._generate_tags()

    def _set_pre_and_next_post(self):
        if len(self.posts) < 2:
            return
        self.posts[0].next_post = self.posts[1]
        self.posts[-1].pre_post = self.posts[-2]
        for i in range(1, len(self.posts) - 1):
            self.posts[i].pre_post = self.posts[i - 1]
            self.posts[i].next_post = self.posts[i + 1]

    def _generate_archives(self):
        archives = dict()
        for post in self.posts:
            if post.archive not in archives:
                archives[post.archive] = []
            archives[post.archive].append(post)
        return archives

    def _generate_tags(self):
        known_tags = dict()
        for post in self.posts:
            for tag in post.tags:
                if tag.slug not in known_tags:
                    known_tags[tag] = []
                known_tags[tag].append(post)
        return known_tags

    def _write(self):
        if os.path.isdir(self.output_path):
            shutil.rmtree(self.output_path)
        os.mkdir(self.output_path)
        os.mkdir(join_path(self.output_path, 'archive'))
        os.mkdir(join_path(self.output_path, 'tag'))
        # load templates
        env = Environment(loader=FileSystemLoader(self.template_path))
        env.filters['format_datetime'] = lambda x: strftime('%Y-%m-%d %H:%M', x)
        self.templates = {
            'index': env.get_template('index.html'),
            'post': env.get_template('post.html'),
            'archive': env.get_template('archive.html'),
            'tag': env.get_template('tag.html')
        }
        # write posts
        for post in self.posts:
            dir_path = join_path(self.output_path, post.slug)
            os.mkdir(dir_path)
            with open(join_path(dir_path, 'index.html'), 'w', encoding='utf-8') as fp:
                output = self.templates['post'].render(
                    content=post.content,
                    title=post.title,
                    next_post=post.next_post,
                    pre_post=post.pre_post,
                    date=post.date,
                    tags=post.tags,
                    archive=post.archive,
                    site=self
                )
                fp.write(output)
        # write homepage
        with open(join_path(self.output_path, 'index.html'), 'w', encoding='utf-8') as fp:
            output = self.templates['index'].render(
                posts=sorted(self.posts[-10:], key=lambda x: x.date, reverse=True),
                site=self
            )
            fp.write(output)
        # write tags
        for tag in self.tags.iterkeys():
            os.mkdir(join_path(self.output_path, 'tag', tag.slug))
            with open(join_path(self.output_path, 'tag', tag.slug, 'index.html'),
                      'w', encoding='utf-8') as fp:
                output = self.templates['tag'].render(
                    posts=sorted(self.tags[tag], key=lambda x: x.date, reverse=True),
                    tag=tag,
                    site=self
                )
                fp.write(output)
        # write archives
        for archive in self.archives.iterkeys():
            os.mkdir(join_path(self.output_path, 'archive', archive))
            with open(join_path(self.output_path, 'archive', archive, 'index.html'),
                      'w', encoding='utf-8') as fp:
                output = self.templates['archive'].render(
                    posts=sorted(self.archives[archive], key=lambda x: x.date, reverse=True),
                    archive=archive,
                    site=self
                )
                fp.write(output)

    def publish(self):
        self._load()
        self._write()
        assert self


def run(blog_path):
    site = Blog(blog_path, config)
    site.publish()

if __name__ == '__main__':
    run(sys.argv[1])