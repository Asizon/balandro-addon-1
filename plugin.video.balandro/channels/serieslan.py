# -*- coding: utf-8 -*-

import sys

if sys.version_info[0] < 3:
    import urllib
else:
    import urllib.parse as urllib


import re

from platformcode import logger, platformtools
from core.item import Item
from core import httptools, scrapertools, servertools, jsontools, tmdb


host = 'https://serieslan.com/'

perpage = 30


def mainlist(item):
    return mainlist_series(item)

def mainlist_series(item):
    logger.info()
    itemlist = []

    itemlist.append(item.clone( title='Catálogo por alfabético (A - Z)', action ='list_all', url = host + 'lista.php?or=abc' ))
    itemlist.append(item.clone( title='Catálogo por alfabético (Z - A)', action ='list_all', url = host + 'lista.php?or=cba' ))

    itemlist.append(item.clone( title='Más populares', action ='list_all', url = host + 'lista.php?or=mas' ))
    itemlist.append(item.clone( title='Más antiguas', action ='list_all', url = host + 'lista.php?or=ler' ))
    itemlist.append(item.clone( title='Más actuales', action ='list_all', url = host + 'lista.php?or=rel' ))
    itemlist.append(item.clone( title='Más impopulares', action ='list_all', url = host + 'lista.php?or=sam' ))

    itemlist.append(item.clone( title = 'Buscar serie ...', action = 'search', search_type = 'tvshow' ))

    return itemlist


def list_all(item):
    logger.info()
    itemlist = []

    if not item.page: item.page = 0

    data = httptools.downloadpage(item.url).data

    patron = ' data-original="([^"]+)"></div>\s*<div class="dt"><a href="([^"]+)" class="gol"><h2>(.*?)</h2></a><span>(.*?)</span>'
    matches = re.compile(patron, re.DOTALL).findall(data)

    num_matches = len(matches)
    desde = item.page * perpage
    hasta = desde + perpage

    for thumb, url, title, year in matches[desde:hasta]:
        itemlist.append(item.clone( action='temporadas', url = host + url, title = title, thumbnail = host + thumb[1:], 
                                    contentType='tvshow', contentSerieName=title, infoLabels={'year': year} ))

    tmdb.set_infoLabels(itemlist)

    if num_matches > hasta:
        itemlist.append(item.clone( title='>> Página siguiente', page=item.page + 1, action='list_all', text_color='coral' ))

    return itemlist


def temporadas(item):
    logger.info()
    itemlist = []

    data = httptools.downloadpage(item.url).data

    matches = scrapertools.find_multiple_matches(data, 'class="select-ss"[^>]*>([^<]*)')

    for n, title in enumerate(matches):
        if not title: title = 'Temporada ' + str( n + 1)

        if len(matches) == 1:
            platformtools.dialog_notification(item.contentSerieName.replace('&#038;', '&'), 'solo [COLOR tan]' + title + '[/COLOR]')
            item.page = 0
            item.contentType = 'season'
            item.contentSeason = n + 1
            itemlist = episodios(item)
            return itemlist

        itemlist.append(item.clone( action='episodios', title = title, contentType = 'season', contentSeason = n + 1, page = 0 ))

    tmdb.set_infoLabels(itemlist)

    return itemlist


def episodios(item):
    logger.info()
    itemlist = []

    if not item.page: item.page = 0
    perpage = 50

    data = httptools.downloadpage(item.url).data

    matches = scrapertools.find_multiple_matches(data, "<div id='ss-(\d+)'>(.*?)</div>")
    if not matches: # Temporada única
        matches = [(0, data)]

    last_epi = 0

    for num_s, episodios in matches[item.page * perpage:]:
        season = int(num_s) + 1

        patron_epi = '<a href="([^"]+)"><li><span><strong>[^<]*</strong>(\d+)[^<]*</span>([^<]+)</li>'
        matches_epi = scrapertools.find_multiple_matches(episodios, patron_epi)

        for url, epi, title in matches_epi:
            # convertir numeración episodios consecutivos
            num_epi = int(epi)

            if item.contentSeason:
                if not str(item.contentSeason) == str(season): continue

            episode = num_epi - last_epi if num_epi > last_epi else num_epi
            titulo = '%sx%s %s' % (season, episode, title)
            if season > 1 and num_epi > last_epi: titulo += ' (%s)' % epi

            itemlist.append(item.clone( action='findvideos', url= host + url, title = titulo, 
                                        contentType = 'episode', contentSeason = season, contentEpisodeNumber = episode ))
        if num_epi: last_epi = num_epi

        if len(itemlist) >= perpage:
            break

    # ~ tmdb.set_infoLabels(itemlist)

    if len(matches) > (item.page + 1) * perpage:
        itemlist.append(item.clone( title=">> Página siguiente", action="episodios", page=item.page + 1, text_color='coral' ))

    return itemlist


def findvideos(item):
    logger.info()
    itemlist = []

    data = httptools.downloadpage(item.url).data

    _sa = re.findall('var _sa = (true|false);', data, flags=re.DOTALL)[0]
    _sl = re.findall("var _sl = \['([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'", data, flags=re.DOTALL)[0]
    if not _sa or not _sl: return itemlist

    aux = _sl[3].lower().replace('(','[').replace(')',']')
    if '[castellano]' in aux: lang = 'Esp'
    elif '[ingles]' in aux: lang = 'Eng'
    else:
        lang = scrapertools.find_single_match(data, '<span>Idioma:\s*</span>([^<]+)')
        if 'Latino' in lang: lang = 'Lat'

    matches = re.findall('<button class="selop" sl="([^"]+)">([^<]+)</button>', data, flags=re.DOTALL)

    for num, nombre in matches:
        url = resuelve_golink(int(num), _sa, _sl)
        server = servertools.corregir_servidor(nombre)

        if server:
            if not servertools.is_server_available(server):
                server = '' # indeterminado
            elif not servertools.is_server_enabled(server):
                continue 

        itemlist.append(Item( channel = item.channel, action = 'play', server = server, language = lang, title = '', url = url, 
                              other = nombre if not server else '' ))

    return itemlist


def resuelve_golink (num, sa, sl):
    b = [3, 10, 5, 22, 31]
    d = ''
    for i in range(len(b)):
        d += sl[2][b[i]+num:b[i]+num+1]

    SVR = "https://viteca.stream" if sa == 'true' else "http://serieslan.com"
    TT = "/" + urllib.quote_plus(sl[3].replace("/", "><")) if num == 0 else ""

    return SVR + "/el/" + sl[0] + "/" + sl[1] + "/" + str(num) + "/" + sl[2] + d + TT


def play(item):
    logger.info()
    itemlist = []

    data = httptools.downloadpage(item.url).data

    from lib import serieslanresolver
    url = serieslanresolver.decode_url(data)

    if url:
        servidor = servertools.get_server_from_url(url)
        servidor = servertools.corregir_servidor(servidor)

        if servidor and (servidor != 'directo' or 'googleusercontent' in url):
            url = servertools.normalize_url(servidor, url)
            itemlist.append(item.clone( url=url, server=servidor ))

    return itemlist


def search(item, texto):
    logger.info()
    itemlist = []

    try:
        data = httptools.downloadpage(host+'b.php', post='k='+texto.replace(' ', '+')).data
        matches = jsontools.load(data)
        for datos in matches['dt']:
            if len(datos) < 4 or not datos[1] or not datos[2]: continue
            itemlist.append(item.clone( title=datos[1], url=host + datos[2], action='temporadas', thumbnail=host + 'tb/' + datos[0] + '.jpg', 
                                        contentType='tvshow', contentSerieName=datos[1], infoLabels={'year': datos[3]} ))

        tmdb.set_infoLabels(itemlist)
    except:
        import sys
        for line in sys.exc_info():
            logger.error("%s" % line)

    return itemlist
