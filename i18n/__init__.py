# SPDX-License-Identifier: GPL-3.0-or-later

import bpy

from . import (
    de_DE,
    en_US,
    es_ES,
    fr_FR,
    it_IT,
    ja_JP,
    ko_KR,
    pl_PL,
    pt_BR,
    ru_RU,
    vi_VN,
    zh_CN,
    zh_TW,
)


TRANSLATIONS = {
    "de": de_DE.TRANSLATIONS,
    "de_DE": de_DE.TRANSLATIONS,
    "en": en_US.TRANSLATIONS,
    "en_US": en_US.TRANSLATIONS,
    "es": es_ES.TRANSLATIONS,
    "es_ES": es_ES.TRANSLATIONS,
    "fr": fr_FR.TRANSLATIONS,
    "fr_FR": fr_FR.TRANSLATIONS,
    "it": it_IT.TRANSLATIONS,
    "it_IT": it_IT.TRANSLATIONS,
    "ja": ja_JP.TRANSLATIONS,
    "ja_JP": ja_JP.TRANSLATIONS,
    "ko": ko_KR.TRANSLATIONS,
    "ko_KR": ko_KR.TRANSLATIONS,
    "pl": pl_PL.TRANSLATIONS,
    "pl_PL": pl_PL.TRANSLATIONS,
    "pt": pt_BR.TRANSLATIONS,
    "pt_BR": pt_BR.TRANSLATIONS,
    "ru": ru_RU.TRANSLATIONS,
    "ru_RU": ru_RU.TRANSLATIONS,
    "vi": vi_VN.TRANSLATIONS,
    "vi_VN": vi_VN.TRANSLATIONS,
    "zh_CN": zh_CN.TRANSLATIONS,
    "zh_HANS": zh_CN.TRANSLATIONS,
    "zh_HANT": zh_TW.TRANSLATIONS,
    "zh_TW": zh_TW.TRANSLATIONS,
}


def register():
    bpy.app.translations.register(__package__, TRANSLATIONS)


def unregister():
    try:
        bpy.app.translations.unregister(__package__)
    except RuntimeError:
        pass
