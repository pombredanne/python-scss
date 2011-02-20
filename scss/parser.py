import cPickle
import logging
import os.path
from collections import defaultdict

from scss.base import CopyNode, Empty, ParseNode, SimpleNode, SemiNode, SepValString, Node
from scss.grammar import STYLESHEET, VAR_DEFINITION, VAL_STRING, SELECTOR_GROUP, DECLARATION, DECLARESET, EXTEND, INCLUDE, MIXIN, MIXIN_PARAM, RULESET, VARIABLE, DEC_NAME, HEXCOLOR, NUMBER_VALUE, NUMBER, SCSS_COMMENT, CSS_COMMENT, FUNCTION, IF, ELSE, IF_CONDITION, IF_BODY, SELECTOR, FOR, FOR_BODY, SEP_VAL_STRING, TERM, MEDIA, DEBUG, EMPTY, CHARSET, FONT_FACE, quotedString, IMPORT, VARIABLES
from scss.value import NumberValue, ColorValue, VarString, Variable, QuotedStringValue
from scss.var import Function, IfNode, ForNode, Mixin, Extend, Include, VarDef


class Comment(Node):
    def __str__(self):
        if self.stylecheet.ignore_comment:
            return ''
        return super(Comment, self).__str__()


class Debug(Empty):
    def __init__(self, t, s):
        super(Debug, self).__init__(t, s)
        logging.debug(str(self))


class SelectorGroup(ParseNode):
    """ Part of css rule.
    """
    def __init__(self, t, s=None):
        super(SelectorGroup, self).__init__(t, s)
        self.data = list(self.data)

    def increase(self, other):
        return SelectorGroup(list( self.data ) + other.data[1:])

    def parse(self, target):
        for x in str(self).split(','):
            target.selectorgroup.append(SelectorGroup( x.strip().split(' ') ))

    def __add__(self, other):
        test = str(other)
        if '&' in test:
            stest = str(self)
            return SelectorGroup(test.replace('&', stest).split())
        else:
            return SelectorGroup(self.data + other.data)


class DeclareSet(ParseNode):
    def __init__(self, t, s):
        self.declaration = []
        super(DeclareSet, self).__init__(t, s)

    def render(self, target):
        name = str(self.data[0])
        for dec in getattr(self, 'declareset', []):
            dec.render(self)
        for dc in self.declaration:
            dc.data[0].data[0] = "-".join((name, dc.data[0].data[0]))
            target.declaration.append(dc)


class Declaration(ParseNode):
    """ Css declaration.
    """
    def __str__(self):
        name, expr = self.data[0].data, self.data[2:]
        return ': '.join([
            ''.join(str(s) for s in name),
            ' '.join(str(e) for e in expr)])


class FontFace(ParseNode):
    def __init__(self, t, s):
        self.declaration = []
        super(FontFace, self).__init__(t, s)

    def __str__(self):
        out = '\n@font-face {\n\t'
        self.declaration.sort(key=lambda x: str(x.data[0]))
        out += ';\n\t'.join(str(d) for d in self.declaration)
        out += '}\n'
        return out


class Ruleset(ParseNode):

    def __init__(self, t, s):
        self.declaration = []
        self.selectorgroup = []
        self.ruleset = []
        super(Ruleset, self).__init__(t, s)
        self.ancor = str(self.data[0].data[0])
        s.rset[self.ancor].add(self)

    def __repr__(self):
        return str(self)

    def parse(self, target):
        super(Ruleset, self).parse(target)
        if isinstance(target, Ruleset):
            self.parse_ruleset(target)

    def parse_ruleset(self, target):
        selgroup = list()
        for psg in target.selectorgroup:
            for sg in self.selectorgroup:
                selgroup.append(psg + sg)
        self.selectorgroup = selgroup

        for r in self.ruleset:
            r.parse_ruleset(target)

    def parse_declareset(self):
        for ds in getattr(self, 'declareset', []):
            ds.render(self)

    def __str__(self):
        out = ''
        self.parse_declareset()
        if len(self.declaration):
            out = '\n'
            out += ', '.join(str(s) for s in self.selectorgroup)
            out += ' {\n\t'
            self.declaration.sort(key=lambda x: str(x.data[0]))
            out += ';\n\t'.join(str(d) for d in self.declaration)
            out += '}\n'
        # for r in getattr(self, 'ruleset', []):
            # out += '\n'.join("%s%s" % (self.dataab, l) for l in str(r).split('\n'))
        out += ''.join(str(r) for r in self.ruleset)
        return out


class Mixinparam(ParseNode):
    @property
    def name(self):
        return self.data[0].data[1]

    @property
    def default(self):
        if len(self.data) > 1:
            return self.data[1]
        return None


class Stylecheet(object):

    defvalue = NumberValue(0)

    def __init__(self, cache = None, ignore_comment=False):
        self.cache = cache or dict(
            ctx = dict(),
            mix = dict(),
            rset = defaultdict(set),
            out = ''
        )
        self.ignore_comment = ignore_comment

        # Comments
        CSS_COMMENT.setParseAction(self.getType(Comment))
        SCSS_COMMENT.setParseAction(lambda s, l, t: '')

        # At rules
        MEDIA.setParseAction(self.getType(SimpleNode))
        IMPORT.setParseAction(self.getType(SemiNode))
        CHARSET.setParseAction(self.getType(SemiNode))
        FONT_FACE.setParseAction(self.getType(FontFace))
        EMPTY.setParseAction(self.getType(Empty))
        VARIABLES.setParseAction(Empty)

        # Values and variables
        HEXCOLOR.setParseAction(ColorValue)
        NUMBER_VALUE.setParseAction(NumberValue)
        NUMBER.setParseAction(NumberValue)
        quotedString.setParseAction(QuotedStringValue)

        VAR_DEFINITION.setParseAction(self.getType(VarDef))
        VARIABLE.setParseAction(self.getType(Variable))
        SEP_VAL_STRING.setParseAction(self.getType(SepValString))
        VAL_STRING.setParseAction(self.getType(VarString))

        # Declarations
        DEC_NAME.setParseAction(self.getType())
        TERM.setParseAction(self.getType())
        DECLARATION.setParseAction(self.getType(Declaration))

        DECLARESET.setParseAction(self.getType(DeclareSet))
        SELECTOR_GROUP.setParseAction(self.getType(SelectorGroup))
        SELECTOR.setParseAction(self.getType())
        RULESET.setParseAction(self.getType(Ruleset))

        MIXIN_PARAM.setParseAction(self.getType(Mixinparam))
        MIXIN.setParseAction(self.getType(Mixin))
        INCLUDE.setParseAction(self.getType(Include))
        EXTEND.setParseAction(self.getType(Extend))

        IF.setParseAction(self.getType(IfNode))
        FOR.setParseAction(self.getType(ForNode))
        FOR_BODY.setParseAction(self.getType(ParseNode))
        IF_CONDITION.setParseAction(self.getType(ParseNode))
        IF_BODY.setParseAction(self.getType(ParseNode))
        ELSE.setParseAction(self.getType(ParseNode))
        FUNCTION.setParseAction(self.getType(Function))
        DEBUG.setParseAction(self.getType(Debug))

    def get_var(self, name):
        """ Get variable from global stylesheet context.
        """
        rec = self.cache['ctx'].get(name)
        return rec[0] if rec else self.defvalue

    def set_var(self, name, value, default=False):
        """ Set variable to global stylesheet context.
        """
        if not(default and self.cache['ctx'].get(name)):
            self.cache['ctx'][name] = value, default

    @property
    def mixctx(self):
        return self.cache['mix']

    @property
    def rset(self):
        return self.cache['rset']

    def __str__(self):
        return self.cache['out']

    def dump(self):
        return cPickle.dumps(self.cache)

    def loads(self, src):
        """ Parse string and return self cache.
        """
        # self.cache['out'] = ''.join(str(e) for e in STYLESHEET.parseString(src, parseAll=True)).strip()
        self.cache['out'] = STYLESHEET.transformString(src.strip()).strip()
        return self.cache

    def update(self, cache):
        """ Update self cache from other.
        """
        self.cache['out'] += cache.get('out')
        self.mixctx.update(cache.get('mix'))
        self.rset.update(cache.get('rset'))
        for name, rec in cache['ctx'].items():
            self.set_var(name, *rec)

    def load(self, f, precache=False):
        name = os.path.splitext(f.name)[0]
        cache_path = '.'.join((name, 'ccss'))
        if os.path.exists(cache_path):
            ptime = os.path.getmtime(cache_path)
            ttime = os.path.getmtime(f.name)
            if ptime > ttime:
                dump = open(cache_path, 'rb').read()
                self.update(cPickle.loads(dump))
                return self.cache

        src = f.read()
        self.loads(src)
        if precache:
            f = open(cache_path, 'wb')
            f.write(self.dump())
        return self.cache

    def parse(self, src):
        self.loads(src)
        return str(self)

    def getType(self, node=CopyNode, style=True):
        def wrap(s, l, t):
            if style:
                return node(t, self)
            return node(t)
        return wrap


def parse( src, cache=None ):
    """ Parse from string.
    """
    parser = Stylecheet(cache)
    return parser.parse(src)


def load(path, cache=None, precache=False):
    """ Parse from file.
    """
    parser = Stylecheet(cache)
    cache = parser.load(path, precache=precache)
    return str(parser)
