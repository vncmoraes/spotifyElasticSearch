import re
import spotipy
import os
import time
from spotipy.oauth2 import SpotifyOAuth
from lyricsgenius import Genius
from pathvalidate import sanitize_filename
from elasticsearch import Elasticsearch
from time import perf_counter

elastic_id = ''
elastic_token = ''
spotify_id = ''
spotify_token = ''
genius_token = ''

es = Elasticsearch(
    cloud_id=elastic_id,
    basic_auth=("elastic", elastic_token)
)

sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        scope='playlist-read-private playlist-read-collaborative user-read-private',  # Permissões concedidas pelo usuário
        client_id=spotify_id,
        client_secret=spotify_token,
        redirect_uri='http://example.com/'  # URL da aplicação
    )
)

genius = Genius(access_token=genius_token, verbose=False)


def list_playlists():
    user_playlists = sp.current_user_playlists()['items']
    playlists_names = ['\nPLaylists encontradas no perfil do usuário:\n']

    for i, playlist in enumerate(user_playlists, start=1):
        playlists_names.append(f'{i} - {playlist["name"]}')

    playlists_names.append('')

    if len(playlists_names) > 2:
        for playlist_name in playlists_names:
            print(playlist_name)
    else:
        print('Nenhuma playlist encontrada no perfil do usuário!')

    return user_playlists


def index_song(playlist_name, song_doc):
    playlist_name = re.sub(r'\W+', '', playlist_name).lower()
    es.index(index=f"{playlist_name}", document=song_doc)


def fetch_playlist_lyrics(playlist):
    playlist_name = '_'.join(sanitize_filename(playlist['name']).split())
    playlist_path = f'users/{sp.current_user().get("id")}/playlists/{playlist_name}'
    songs = []
    offset = 0

    while True:
        partial_songs = sp.playlist_items(playlist['uri'], offset=offset)['items']

        if len(partial_songs) <= 0:
            break

        songs.extend(partial_songs)
        offset += 100

    if not os.path.exists(playlist_path):
        os.makedirs(playlist_path)

    print()

    for song_index, song in enumerate(songs, start=1):
        print(f'{song_index}/{len(songs)} letras salvas')
        song_info = song['track']

        if song_info['type'] != 'track':
            continue

        song_title = song_info['name']
        artist_name = song_info['album']['artists'][0]['name']
        song = sanitize_filename(f'{song_title} - {artist_name}')
        song_path = rf'{playlist_path}/{song}.txt'

        if not os.path.exists(song_path):
            genius_song = None

            for i in range(3):
                try:
                    genius_song = genius.search_song(title=song_title, artist=artist_name)
                    break
                except:
                    continue

            if genius_song:
                with open(song_path, "w", encoding='utf8') as f:
                    f.write(genius_song.lyrics)
                    song_info = {'artist': artist_name, 'title': song_title, 'lyrics': genius_song.lyrics}
                    index_song(playlist_name, song_info)




def elastic_search_songs_by_keyword(playlist_name, keyword):
    elastic_search_start = perf_counter()
    playlist_name = re.sub(r'\W+', '', playlist_name).lower()
    es.indices.refresh(index=f"{playlist_name}")
    resp = es.search(index=f"{playlist_name}", query={"multi_match": {"query": f"{keyword}"}}, size=10000)
    songs_found = len(resp["hits"]["hits"])

    if songs_found > 0:
        print(f'\nMúsicas encontradas com a palavra "{keyword}": {songs_found}\n')

        for song in resp['hits']['hits']:
            song_info = song['_source']
            print(f'{song_info["title"]} - {song_info["artist"]}')
    else:
        print(f'Nenhuma música encontrada com a palavra "{keyword}"\n')

    return perf_counter() - elastic_search_start




def search_songs_by_keyword(playlist_name, keyword):
    common_search_start = perf_counter()

    playlist_path = f'users/{sp.current_user().get("id")}/playlists/{playlist_name}'
    files = os.listdir(playlist_path)

    for file in files:
        with open(os.path.join(playlist_path, file), "r", encoding='utf8') as f:
            if keyword.lower() in f.read().lower().split():
                time.sleep(0.2)

    return perf_counter() - common_search_start


if __name__ == '__main__':
    playlists = list_playlists()

    if playlists:
        while True:
            index_playlist = int(
                re.sub('\D+', '', input('Digite o número correspondente à playlist desejada: ')) or 0) - 1

            if 0 <= index_playlist < len(playlists):
                selected_playlist = playlists[index_playlist]
                playlist_name = '_'.join(sanitize_filename(selected_playlist['name']).split())
                print(f'Playlist selecionada: {selected_playlist["name"]}\n')
                keyword = input('Digite a palavra que deseja buscar nas letras: ')
                fetch_playlist_lyrics(selected_playlist)  # Busca as letras de todas as músicas da playlist

                elapsed_time_elastic_search = elastic_search_songs_by_keyword(playlist_name, keyword)
                elapsed_time_common_search = search_songs_by_keyword(playlist_name, keyword)

                print(f'\nTempo de busca Elasticsearch: {elapsed_time_elastic_search}')
                print(f'Tempo de busca sequencial em disco: {elapsed_time_common_search}')
                break

            else:
                print('O número digitado não corresponde à nenhuma playlist!\n')
