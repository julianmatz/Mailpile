from gettext import gettext as _

import mailpile.config
from mailpile.commands import Command
from mailpile.plugins import PluginManager
from mailpile.urlmap import UrlMap
from mailpile.util import *

from mailpile.plugins.search import Search


_plugins = PluginManager(builtin=__file__)


##[ Configuration ]###########################################################


FILTER_TYPES = ('user',      # These are the default, user-created filters
                'incoming',  # These filters are only applied to new messages
                'system',    # Mailpile core internal filters
                'plugin')    # Filters created by plugins

_plugins.register_config_section('tags', ["Tags", {
    'name': ['Tag name', 'str', ''],
    'slug': ['URL slug', 'slashslug', ''],

    # Functional attributes
    'type': ['Tag type', [
        'tag', 'group', 'attribute', 'unread',
        # Maybe TODO: 'folder', 'shadow',
        'drafts', 'blank', 'outbox', 'sent',          # composing and sending
        'replied', 'fwded', 'tagged', 'read', 'ham',  # behavior tracking tags
        'trash', 'spam'                               # junk mail tags
    ], 'tag'],
    'flag_hides': ['Hide tagged messages from searches?', 'bool', False],
    'flag_editable': ['Mark tagged messages as editable?', 'bool', False],

    # Tag display attributes for /in/tag or searching in:tag
    'template': ['Default tag display template', 'str', 'index'],
    'search_terms': ['Terms to search for on /in/tag/', 'str', 'in:%(slug)s'],
    'search_order': ['Default search order for /in/tag/', 'str', ''],
    'magic_terms': ['Extra terms to search for', 'str', ''],

    # Tag display attributes for search results/lists/UI placement
    'icon': ['URL to default tag icon', 'url', 'icon-tag'],
    'label': ['Display as label in results', 'bool', True],
    'label_color': ['Color to use in label', 'str', '#4D4D4D'],
    'display': ['Display context in UI', ['priority', 'tag', 'subtag',
                                          'archive', 'invisible'], 'tag'],
    'display_order': ['Order in lists', 'float', 0],
    'parent': ['ID of parent tag, if any', 'str', ''],

    # Outdated crap
    'hides_flag': ['DEPRECATED', 'ignore', None],
    'write_flag': ['DEPRECATED', 'ignore', None],
}, {}])

_plugins.register_config_section('filters', ["Filters", {
    'tags': ['Tag/untag actions', 'str', ''],
    'terms': ['Search terms', 'str', ''],
    'comment': ['Human readable description', 'str', ''],
    'type': ['Filter type', FILTER_TYPES, FILTER_TYPES[0]],
}, {}])

_plugins.register_config_variables('sys', {
    'writable_tags': ['DEPRECATED', 'str', []],
    'invisible_tags': ['DEPRECATED', 'str', []],
})

#INFO_HIDES_TAG_METADATA = ('flag_editable', 'flag_hides')


def GetFilters(cfg, filter_on=None, types=FILTER_TYPES[:1]):
    filters = cfg.filters.keys()
    filters.sort(key=lambda k: int(k, 36))
    flist = []
    tset = set(types)
    for fid in filters:
        terms = cfg.filters[fid].get('terms', '')
        ftype = cfg.filters[fid]['type']
        if not (set([ftype, 'any', 'all', None]) & tset):
            continue
        if filter_on is not None and terms != filter_on:
            continue
        flist.append((fid, terms,
                      cfg.filters[fid].get('tags', ''),
                      cfg.filters[fid].get('comment', ''),
                      ftype))
    return flist


def MoveFilter(cfg, filter_id, filter_new_id):
    def swap(f1, f2):
        tmp = cfg.filters[f1]
        cfg.filters[f1] = cfg.filters[f2]
        cfg.filters[f2] = tmp
    ffrm = int(filter_id, 36)
    fto = int(filter_new_id, 36)
    if ffrm > fto:
        for fid in reversed(range(fto, ffrm)):
            swap(b36(fid + 1), b36(fid))
    elif ffrm < fto:
        for fid in range(ffrm, fto):
            swap(b36(fid), b36(fid + 1))


def GetTags(cfg, tn=None, default=None, **kwargs):
    results = []
    if tn is not None:
        # Hack, allow the tn= to be any of: TID, name or slug.
        tn = tn.lower()
        try:
            if tn in cfg.tags:
                results.append([cfg.tags[tn]._key])
        except (KeyError, IndexError, AttributeError):
            pass
        if not results:
            tv = cfg.tags.values()
            tags = ([t._key for t in tv if t.slug.lower() == tn] or
                    [t._key for t in tv if t.name.lower() == tn])
            results.append(tags)

    if kwargs:
        tv = cfg.tags.values()
        for kw in kwargs:
            want = unicode(kwargs[kw]).lower()
            results.append([t._key for t in tv
                            if (want == '*' or
                                unicode(t[kw]).lower() == want)])

    if (tn or kwargs) and not results:
        return default
    else:
        tags = set(cfg.tags.keys())
        for r in results:
            tags &= set(r)
        tags = [cfg.tags[t] for t in tags]
        if 'display' in kwargs:
            tags.sort(key=lambda k: (k.get('display_order', 0), k.slug))
        else:
            tags.sort(key=lambda k: k.slug)
        return tags


def GetTag(cfg, tn, default=None):
    return (GetTags(cfg, tn, default=None) or [default])[0]


def GetTagID(cfg, tn):
    tags = GetTags(cfg, tn=tn, default=[None])
    return tags and (len(tags) == 1) and tags[0]._key or None


def GetTagInfo(cfg, tn, stats=False, unread=None, exclude=None, subtags=None):
    tag = GetTag(cfg, tn)
    tid = tag._key
    info = {
        'tid': tid,
        'url': UrlMap(config=cfg).url_tag(tid),
    }
    for k in tag.all_keys():
#       if k not in INFO_HIDES_TAG_METADATA:
            info[k] = tag[k]
    if subtags:
        info['subtag_ids'] = [t._key for t in subtags]
    exclude = exclude or set()
    if stats and (unread is not None):
        messages = (cfg.index.TAGS.get(tid, set()) - exclude)
        stats_all = len(messages)
        info['stats'] = {
            'all': stats_all,
            'new': len(messages & unread),
            'not': len(cfg.index.INDEX) - stats_all
        }
        if subtags:
            for subtag in subtags:
                messages |= cfg.index.TAGS.get(subtag._key, set())
            info['stats'].update({
                'sum_all': len(messages),
                'sum_new': len(messages & unread),
            })

    return info


# FIXME: Is this bad form or awesome?  This is used in a few places by
#        commands.py and search.py, but might be a hint that the plugin
#        architecture needs a little more polishing.
mailpile.config.ConfigManager.get_tag = GetTag
mailpile.config.ConfigManager.get_tags = GetTags
mailpile.config.ConfigManager.get_tag_id = GetTagID
mailpile.config.ConfigManager.get_tag_info = GetTagInfo
mailpile.config.ConfigManager.get_filters = GetFilters
mailpile.config.ConfigManager.filter_move = MoveFilter


##[ Commands ]################################################################

class TagCommand(Command):
    def slugify(self, tag_name):
        return CleanText(tag_name.lower().replace(' ', '-'),
                         banned=CleanText.NONDNS.replace('/', '')
                         ).clean.lower()

    def _reorder_all_tags(self):
        taglist = [(t.display, t.display_order, t.slug, t._key)
                   for t in self.session.config.tags.values()]
        taglist.sort()
        order = 1
        for td, tdo, ts, tid in taglist:
            self.session.config.tags[tid].display_order = order
            order += 1

    def finish(self, save=True):
        idx = self._idx()
        if save:
            # Background save makes things feel fast!
            def background():
                if idx:
                    idx.save_changes()
                self.session.config.save()
            self._background('Save index', background)


class Tag(TagCommand):
    """Add or remove tags on a set of messages"""
    SYNOPSIS = (None, 'tag', 'tag', '<[+|-]tags> <msgs>')
    ORDER = ('Tagging', 0)
    HTTP_CALLABLE = ('POST', )
    HTTP_POST_VARS = {
        'mid': 'message-ids',
        'add': 'tags',
        'del': 'tags'
    }

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            if not self.result['msg_ids']:
                return 'Nothing happened'
            what = []
            if self.result['tagged']:
                what.append('Tagged ' +
                            ', '.join([k['name'] for k
                                       in self.result['tagged']]))
            if self.result['untagged']:
                what.append('Untagged ' +
                            ', '.join([k['name'] for k
                                       in self.result['untagged']]))
            return '%s (%d messages)' % (', '.join(what),
                                         len(self.result['msg_ids']))

    def command(self, save=True, auto=False):
        idx = self._idx()

        if 'mid' in self.data:
            msg_ids = [int(m.replace('=', ''), 36) for m in self.data['mid']]
            ops = (['+%s' % t for t in self.data.get('add', []) if t] +
                   ['-%s' % t for t in self.data.get('del', []) if t])
        else:
            words = list(self.args)
            ops = []
            while words and words[0][0] in ('-', '+'):
                ops.append(words.pop(0))
            msg_ids = self._choose_messages(words)

        rv = {'msg_ids': [], 'tagged': [], 'untagged': []}
        rv['msg_ids'] = [b36(i) for i in msg_ids]
        for op in ops:
            tag = self.session.config.get_tag(op[1:])
            if tag:
                tag_id = tag._key
                tag = tag.copy()
                tag["tid"] = tag_id
                conversation = ('flat' not in (self.session.order or ''))
                if op[0] == '-':
                    idx.remove_tag(self.session, tag_id, msg_idxs=msg_ids,
                                   conversation=conversation)
                    rv['untagged'].append(tag)
                else:
                    idx.add_tag(self.session, tag_id, msg_idxs=msg_ids,
                                conversation=conversation)
                    rv['tagged'].append(tag)
                # Record behavior
                if len(msg_ids) < 15:
                    for t in self.session.config.get_tags(type='tagged'):
                        idx.add_tag(self.session, t._key, msg_idxs=msg_ids)
            else:
                self.session.ui.warning('Unknown tag: %s' % op)

        self.finish(save=save)
        return self._success(_('Tagged %d messagse') % len(msg_ids), rv)


class AddTag(TagCommand):
    """Create a new tag"""
    SYNOPSIS = (None, 'tags/add', 'tags/add', '<tag>')
    ORDER = ('Tagging', 0)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_POST_VARS = {
        'name': 'tag name',
        'slug': 'tag slug',
        # Optional initial attributes of tags
        'icon': 'icon-tag',
        'label': 'display as label in search results, or not',
        'label_color': '03-gray-dark',
        'display': 'tag display type',
        'template': 'tag template type',
        'search_terms': 'default search associated with this tag',
        'magic_terms': 'magic search terms associated with this tag',
        'parent': 'parent tag ID',
    }
    OPTIONAL_VARS = ['icon', 'label', 'label_color', 'display', 'template',
                     'search_terms', 'parent']

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            if not self.result['added']:
                return 'Nothing happened'
            return ('Added tags: ' +
                    ', '.join([k['name'] for k in self.result['added']]))

    def command(self, save=True):
        config = self.session.config

        if self.data.get('_method', 'not-http').upper() == 'GET':
            return self._success(_('Add tags here!'), {
                'form': self.HTTP_POST_VARS,
                'rules': self.session.config.tags.rules['_any'][1]._RULES
            })

        slugs = self.data.get('slug', [])
        names = self.data.get('name', [])
        if slugs and len(names) != len(slugs):
            return self._error('Name/slug pairs do not match')
        elif names and not slugs:
            slugs = [self.slugify(n) for n in names]
        slugs.extend([self.slugify(s) for s in self.args])
        names.extend(self.args)

        for slug in slugs:
            if slug != self.slugify(slug):
                return self._error('Invalid tag slug: %s' % slug)

        for tag in config.tags.values():
            if tag.slug in slugs:
                return self._error('Tag already exists: %s/%s' % (tag.slug,
                                                                  tag.name))

        tags = [{'name': n, 'slug': s} for (n, s) in zip(names, slugs)]
        for v in self.OPTIONAL_VARS:
            for i in range(0, len(tags)):
                vlist = self.data.get(v, [])
                if len(vlist) > i and vlist[i]:
                    tags[i][v] = vlist[i]
        if tags:
            config.tags.extend(tags)
            self._reorder_all_tags()
            self.finish(save=save)

        return self._success(_('Added %d tags') % len(tags),
                             {'added': tags})


class ListTags(TagCommand):
    """List tags"""
    SYNOPSIS = (None, 'tags', 'tags', '[<wanted>|!<wanted>] [...]')
    ORDER = ('Tagging', 0)
    HTTP_STRICT_VARS = False

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            tags = self.result['tags']
            wrap = int(78 / 23)  # FIXME: Magic number
            text = []
            for i in range(0, len(tags)):
                stats = tags[i]['stats']
                text.append(('%s%5.5s %-18.18s'
                             ) % ((i % wrap) == 0 and '  ' or '',
                                  '%s' % (stats.get('sum_new', stats['new'])
                                          or ''),
                                  tags[i]['name'])
                            + ((i % wrap) == (wrap - 1) and '\n' or ''))
            return ''.join(text) + '\n'

    def command(self):
        result, idx = [], self._idx()

        args = []
        search = {}
        for arg in self.args:
            if '=' in arg:
                kw, val = arg.split('=', 1)
                search[kw.strip()] = val.strip()
            else:
                args.append(arg)
        for kw in self.data:
            if kw in self.session.config.tags.rules:
                search[kw] = self.data[kw]

        wanted = [t.lower() for t in args if not t.startswith('!')]
        unwanted = [t[1:].lower() for t in args if t.startswith('!')]
        wanted.extend([t.lower() for t in self.data.get('only', [])])
        unwanted.extend([t.lower() for t in self.data.get('not', [])])

        unread_messages = set()
        for tag in self.session.config.get_tags(type='unread'):
            unread_messages |= idx.TAGS.get(tag._key, set())

        excluded_messages = set()
        for tag in self.session.config.get_tags(flag_hides=True):
            excluded_messages |= idx.TAGS.get(tag._key, set())

        mode = search.get('mode', 'default')
        if 'mode' in search:
            del search['mode']

        for tag in self.session.config.get_tags(**search):
            if wanted and tag.slug.lower() not in wanted:
                continue
            if unwanted and tag.slug.lower() in unwanted:
                continue
            if mode == 'tree' and tag.parent and not wanted:
                continue

            # Hide invisible tags by default, any search terms at all will
            # disable this behavior
            if (not wanted and not unwanted and not search
                    and tag.display == 'invisible'):
                continue

            recursion = self.data.get('_recursion', 0)
            tid = tag._key

            # List subtags...
            if recursion == 0:
                subtags = self.session.config.get_tags(parent=tid)
                subtags.sort(key=lambda k: (k.get('display_order', 0), k.slug))
            else:
                subtags = None

            # Get tag info (how depends on whether this is a hiding tag)
            if tag.flag_hides:
                info = GetTagInfo(self.session.config, tid, stats=True,
                                  unread=unread_messages,
                                  subtags=subtags)
            else:
                info = GetTagInfo(self.session.config, tid, stats=True,
                                  unread=unread_messages,
                                  exclude=excluded_messages,
                                  subtags=subtags)

            # This expands out the full tree
            if subtags and recursion == 0:
                if mode in ('both', 'tree') or (wanted and mode != 'flat'):
                    info['subtags'] = ListTags(self.session,
                                               arg=[t.slug for t in subtags],
                                               data={'_recursion': 1}
                                               ).run().result['tags']

            result.append(info)
        return self._success(_('Listed %d tags') % len(result), {
            'search': search,
            'wanted': wanted,
            'unwanted': unwanted,
            'tags': result
        })


class DeleteTag(TagCommand):
    """Delete a tag"""
    SYNOPSIS = (None, 'tags/delete', 'tags/delete', '<tag>')
    ORDER = ('Tagging', 0)
    HTTP_CALLABLE = ('POST', 'DELETE')
    HTTP_POST_VARS = {
        "tag" : "tag(s) to delete"
    }

    class CommandResult(TagCommand.CommandResult):
        def as_text(self):
            if not self.result:
                return 'Failed'
            if not self.result['removed']:
                return 'Nothing happened'
            return ('Removed tags: ' +
                    ', '.join([k['name'] for k in self.result['removed']]))

    def command(self):
        session, config = self.session, self.session.config
        clean_session = mailpile.ui.Session(config)
        clean_session.ui = session.ui
        result = []

        tag_names = []
        if self.args:
            tag_names = list(self.args)
        elif self.data.get('tag', []):
            tag_names = self.data.get('tag', [])

        for tag_name in tag_names:

            tag = config.get_tag(tag_name)

            if tag:
                tag_id = tag._key

                # FIXME: Refuse to delete tag if in use by filters

                rv = (Search(clean_session, arg=['tag:%s' % tag_id]).run() and
                      Tag(clean_session, arg=['-%s' % tag_id, 'all']).run())
                if rv:
                    del config.tags[tag_id]
                    result.append({'name': tag.name, 'tid': tag_id})
                else:
                    raise Exception('That failed: %s' % rv)
            else:
                self._error('No such tag %s' % tag_name)
        if result:
            self._reorder_all_tags()
            self.finish(save=True)
        return self._success(_('Deleted %d tags') % len(result),
                             {'removed': result})


class FilterCommand(Command):
    def finish(self, save=True):
        def save_filter():
            self.session.config.save()
            if self.session.config.index:
                self.session.config.index.save_changes()
            return True
        if save:
            self._serialize('Save filter', save_filter)


class Filter(FilterCommand):
    """Add auto-tag rule for current search or terms"""
    SYNOPSIS = (None, 'filter', None, '[new|read] [notag] [=<mid>] '
                                      '[<terms>] [+<tag>] [-<tag>] '
                                      '[<comment>]')
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ('POST', )

    def command(self, save=True):
        session, config = self.session, self.session.config
        args = list(self.args)

        flags = []
        while args and args[0] in ('add', 'set', 'new', 'read', 'notag'):
            flags.append(args.pop(0))

        if args and args[0] and args[0][0] == '=':
            filter_id = args.pop(0)[1:]
        else:
            filter_id = None

        if args and args[0] and args[0][0] == '@':
            filter_type = args.pop(0)[1:]
        else:
            filter_type = FILTER_TYPES[0]

        auto_tag = False
        if 'read' in flags:
            terms = ['@read']
        elif 'new' in flags:
            terms = ['*']
        elif args[0] and args[0][0] not in ('-', '+'):
            terms = []
            while args and args[0][0] not in ('-', '+'):
                terms.append(args.pop(0))
        else:
            terms = session.searched
            auto_tag = True

        if not terms or (len(args) < 1):
            raise UsageError('Need flags and search terms or a hook')

        tags, tids = [], []
        while args and args[0][0] in ('-', '+'):
            tag = args.pop(0)
            tags.append(tag)
            tids.append(tag[0] + config.get_tag_id(tag[1:]))

        if not args:
            args = ['Filter for %s' % ' '.join(tags)]

        if auto_tag and 'notag' not in flags:
            if not Tag(session, arg=tags + ['all']).run(save=False):
                raise UsageError()

        filter_dict = {
            'comment': ' '.join(args),
            'terms': ' '.join(terms),
            'tags': ' '.join(tids),
            'type': filter_type
        }
        if filter_id:
            config.filters[filter_id] = filter_dict
        else:
            config.filters.append(filter_dict)

        self.finish(save=save)
        return True


class DeleteFilter(FilterCommand):
    """Delete an auto-tagging rule"""
    SYNOPSIS = (None, 'filter/delete', None, '<filter-id>')
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ('POST', 'DELETE')

    def command(self):
        session, config = self.session, self.session.config
        if len(self.args) < 1:
            raise UsageError('Delete what?')

        removed = 0
        filters = config.get('filter', {})
        filter_terms = config.get('filter_terms', {})
        args = list(self.args)
        for fid in self.args:
            if fid not in filters:
                match = [f for f in filters if filter_terms[f] == fid]
                if match:
                    args.remove(fid)
                    args.extend(match)

        for fid in args:
            if (config.parse_unset(session, 'filter:%s' % fid)
                    and config.parse_unset(session, 'filter_tags:%s' % fid)
                    and config.parse_unset(session, 'filter_terms:%s' % fid)):
                removed += 1
            else:
                session.ui.warning('Failed to remove %s' % fid)
        if removed:
            self.finish()
        return True


class ListFilters(Command):
    """List (all) auto-tagging rules"""
    SYNOPSIS = (None, 'filter/list', 'filter/list', '[<search>|=<id>|@<type>]')
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'search': 'Text to search for',
        'id': 'Filter ID',
        'type': 'Filter type'
    }

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result is False:
                return unicode(self.result)
            return '\n'.join([('%3.3s %-10s %-18s %-18s %s'
                               ) % (r['fid'], r['type'],
                                    r['terms'], r['human_tags'], r['comment'])
                              for r in self.result])

    def command(self, want_fid=None):
        results = []
        for (fid, trms, tags, cmnt, ftype
             ) in self.session.config.get_filters(filter_on=None,
                                                  types=['all']):
            if want_fid and fid != want_fid:
                continue

            human_tags = []
            for tterm in tags.split():
                tagname = self.session.config.tags.get(
                    tterm[1:], {}).get('slug', '(None)')
                human_tags.append('%s%s' % (tterm[0], tagname))

            skip = False
            args = list(self.args)
            args.extend([t for t in self.data.get('search', [])])
            args.extend(['='+t for t in self.data.get('id', [])])
            args.extend(['@'+t for t in self.data.get('type', [])])
            if args and not want_fid:
                for term in args:
                    term = term.lower()
                    if term.startswith('='):
                        if (term[1:] != fid):
                            skip = True
                    elif term.startswith('@'):
                        if (term[1:] != ftype):
                            skip = True
                    elif ((term not in ' '.join(human_tags).lower())
                            and (term not in trms.lower())
                            and (term not in cmnt.lower())):
                        skip = True
            if skip:
                continue

            results.append({
                'fid': fid,
                'terms': trms,
                'tags': tags,
                'human_tags': ' '.join(human_tags),
                'comment': cmnt,
                'type': ftype
            })
        return results


class MoveFilter(ListFilters):
    """Move an auto-tagging rule"""
    SYNOPSIS = (None, 'filter/move', None, '<filter-id> <position>')
    ORDER = ('Tagging', 1)
    HTTP_CALLABLE = ('POST', 'UPDATE')

    def command(self):
        self.session.config.filter_move(self.args[0], self.args[1])
        self.session.config.save()
        return ListFilters.command(self, want_fid=self.args[1])


_plugins.register_commands(Tag, AddTag, DeleteTag, ListTags,
                           Filter, DeleteFilter,
                           MoveFilter, ListFilters)
