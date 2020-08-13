from typing import List

from spacy.language import Language
from spacy.tokens import Doc, Span, Token

__all__ = [
    "BUNSETU_HEAD_SUFFIX",
    "PHRASE_RELATIONS",
    "POS_PHRASE_MAP",
    "bunsetu_span",
    "bunsetu_phrase_span",
    "bunsetu_head_list",
    "bunsetu_head_tokens",
    "bunsetu_bi_labels",
    "BunsetuRecognizer",
    "append_bunsetu_head_dep_suffix",
]


BUNSETU_HEAD_SUFFIX = "_bunsetu"

PHRASE_RELATIONS = ("compound", "nummod", "nmod")

POS_PHRASE_MAP = {
    "NOUN": "NP",
    "NUM": "NP",
    "PRON": "NP",
    "PROPN": "NP",

    "VERB": "VP",

    "ADJ": "ADJP",

    "ADV": "ADVP",

    "CCONJ": "CCONJP",
}


def bunsetu_head_list(span: Span) -> List[int]:
    doc = span.doc
    heads = doc.user_data["bunsetu_heads"]
    return [i - span.start for i in heads if span.start <= i < span.end]


def bunsetu_head_tokens(span: Span) -> List[Token]:
    doc = span.doc
    heads = doc.user_data["bunsetu_heads"]
    return [span[i - span.start] for i in heads if span.start <= i < span.end]


def bunsetu_spans(span: Span) -> List[Span]:
    return [
        bunsetu_span(head) for head in bunsetu_head_tokens(span)
    ]


def bunsetu_span(bunsetu_head_token: Token) -> Span:
    bunsetu_bi_list = bunsetu_bi_labels(bunsetu_head_token.doc)
    begin = bunsetu_head_token.i
    end = begin + 1
    for idx in range(begin, 0, -1):
        if bunsetu_bi_list[idx] == "B":
            begin = idx
            break
    else:
        begin = 0
    doc_len = len(bunsetu_head_token.doc)
    for idx in range(end, doc_len):
        if bunsetu_bi_list[idx] == "B":
            end = idx
            break
    else:
        end = doc_len

    doc = bunsetu_head_token.doc
    return doc[begin:end]


def bunsetu_phrase_span(bunsetu_head_token: Token, phrase_relations: List[str] = PHRASE_RELATIONS) -> Span:
    def _traverse(token, result):
        for t in token.children:
            if t.i not in heads:
                if t.dep_ in phrase_relations:
                    _traverse(t, result)
        result.append(token.i)
    heads = [t.i for t in bunsetu_head_tokens(bunsetu_head_token.doc)]
    phrase_tokens = []
    _traverse(bunsetu_head_token, phrase_tokens)
    begin = min(phrase_tokens)
    end = max(phrase_tokens) + 1
    doc = bunsetu_head_token.doc
    span = doc[begin:end]
    span.label_ = POS_PHRASE_MAP.get(bunsetu_head_token.pos_, None)
    return span


def bunsetu_bi_labels(span: Span) -> List[str]:
    doc = span.doc
    bunsetu_bi = doc.user_data["bunsetu_bi_labels"]
    return bunsetu_bi[span.start:span.end]


class BunsetuRecognizer:
    def __init__(self, nlp: Language, **_cfg) -> None:
        self.nlp = nlp

    def __call__(self, doc: Doc, debug: bool = False) -> Doc:
        heads = [False] * len(doc)
        for t in doc:
            if t.dep_ == "ROOT":
                heads[t.i] = True
            elif t.dep_.endswith(BUNSETU_HEAD_SUFFIX):
                heads[t.i] = True
                t.dep_ = t.dep_[:-len(BUNSETU_HEAD_SUFFIX)]
        for t in doc:  # recovering uncovered subtrees
            if heads[t.i]:
                while t.head.i < t.i and not heads[t.head.i]:
                    heads[t.head.i] = t.head.pos_ not in {"PUNCT"}
                    if debug and heads[t.head.i]:
                        print("========= A", t.i + 1, t.orth_, "=========")
                        print(list((t.i + 1, t.orth_, t.head.i + 1) for t, is_head in zip(doc, heads) if is_head))
                    t = t.head
                heads[t.head.i] = True

        for ent in doc.ents:  # removing head inside ents
            head = ent.root
            if head is not None:
                for t in ent:
                    if t.i != head:
                        heads[t.i] = False

        """
        for t in doc:
            if heads[t.i]:
                continue
            if t.i < t.head.i:
                for idx in range(t.i + 1, t.head.i):
                    if heads[idx]:
                        heads[t.i] = t.pos_ not in {"PUNCT"}
                        if debug and heads[t.i]:
                            print("========= B", t.i + 1, t.orth_, "=========")
                            print(list((t.i + 1, t.orth_, t.head.i + 1) for t, is_head in zip(doc, heads) if is_head))
                        break
            else:
                for idx in range(t.head.i + 1, t.i):
                    if heads[idx]:
                        heads[t.i] = t.pos_ not in {"PUNCT"}
                        if debug and heads[t.i]:
                            print("========= C", t.i + 1, t.orth_, "=========")
                            print(list((t.i + 1, t.orth_, t.head.i + 1) for t, is_head in zip(doc, heads) if is_head))
                        break
        """
        bunsetu_heads = tuple(idx for idx, is_head in enumerate(heads) if is_head)

        bunsetu_bi = ["I"] * len(doc)
        next_begin = 0
        for head_i in bunsetu_heads:
            t = doc[head_i]
            if next_begin < len(bunsetu_bi):
                bunsetu_bi[next_begin] = "B"
            right = t
            for sub in t.rights:
                if heads[sub.i]:
                    right = right.right_edge
                    break
                right = sub
            next_begin = right.i + 1

        doc.user_data["bunsetu_heads"] = bunsetu_head_list
        doc.user_data["bunsetu_bi_labels"] = bunsetu_bi

        return doc


def append_bunsetu_head_dep_suffix(tokens: List[Token], suffix: str = "_bunsetu") -> None:
    if not suffix:
        return
    for token in tokens:
        if token.dep_.lower() == "root":
            return
        if token.head.i < tokens[0].i or tokens[-1].i < token.head.i:
            token.dep_ += suffix
            return
