from tmdbv3api import TMDb, Movie, TV, Search, Discover, Genre as TMDBGenre, Season as TMDBSeason
from app.core.config import settings
from app.models.schemas import (
    MediaMeta, MediaDetail, SearchResult, 
    Person, Genre, Season, Episode
)
from typing import Optional, List, Any

class TMDBService:
    def __init__(self):
        self.tmdb = TMDb()
        self.tmdb.api_key = settings.TMDB_API_KEY
        self.tmdb.language = settings.TMDB_LANGUAGE
        self.tmdb.debug = False
        
        self.movie_api = Movie()
        self.tv_api = TV()
        self.search_api = Search()
        self.discover_api = Discover()
        self.genre_api = TMDBGenre()
        self.season_api = TMDBSeason()

    def _ensure_list(self, obj: Any) -> List:
        """强制转为 List"""
        if obj is None:
            return []
        if isinstance(obj, list):
            return obj
        try:
            return list(obj)
        except TypeError:
            return []

    def _get_attr(self, obj: Any, key: str, default: Any = None) -> Any:
        """安全获取属性"""
        if hasattr(obj, key):
            val = getattr(obj, key)
            return val if val is not None else default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return default

    def _get_image_url(self, path, size="w500"):
        return f"https://image.tmdb.org/t/p/{size}{path}" if path else None

    def _parse_basic(self, item, media_type_override=None) -> MediaMeta:
        m_type = self._get_attr(item, 'media_type', media_type_override)
        if not m_type:
            if hasattr(item, 'title'): m_type = 'movie' 
            elif hasattr(item, 'name'): m_type = 'tv'
            else: m_type = 'movie'

        title = self._get_attr(item, 'title', self._get_attr(item, 'name', 'Unknown'))
        orig_title = self._get_attr(item, 'original_title', self._get_attr(item, 'original_name', 'Unknown'))
        date = self._get_attr(item, 'release_date', self._get_attr(item, 'first_air_date', ''))
        
        g_ids = self._ensure_list(self._get_attr(item, 'genre_ids', []))

        return MediaMeta(
            tmdb_id=item.id,
            title=title,
            original_title=orig_title,
            media_type=m_type,
            release_date=date,
            poster_path=self._get_image_url(self._get_attr(item, 'poster_path')),
            backdrop_path=self._get_image_url(self._get_attr(item, 'backdrop_path'), "original"),
            overview=self._get_attr(item, 'overview', ''),
            vote_average=self._get_attr(item, 'vote_average', 0.0),
            genre_ids=g_ids
        )

    def _parse_credits(self, credits_obj):
        cast = []
        directors = []
        
        raw_cast = self._get_attr(credits_obj, 'cast')
        safe_cast = self._ensure_list(raw_cast)
        
        for c in safe_cast[:15]:
            cast.append(Person(
                id=self._get_attr(c, 'id'),
                name=self._get_attr(c, 'name'),
                character=self._get_attr(c, 'character'),
                profile_path=self._get_image_url(self._get_attr(c, 'profile_path'))
            ))
        
        raw_crew = self._get_attr(credits_obj, 'crew')
        safe_crew = self._ensure_list(raw_crew)

        for c in safe_crew:
            if self._get_attr(c, 'job') == 'Director':
                directors.append(Person(
                    id=self._get_attr(c, 'id'),
                    name=self._get_attr(c, 'name'),
                    job='Director',
                    profile_path=self._get_image_url(self._get_attr(c, 'profile_path'))
                ))
        return directors, cast

    def get_details_full(self, media_type: str, tmdb_id: int) -> MediaDetail:
        append_str = "credits,recommendations,similar"
        
        if media_type == 'movie':
            data = self.movie_api.details(tmdb_id, append_to_response=append_str)
        else:
            data = self.tv_api.details(tmdb_id, append_to_response=append_str)

        basic = self._parse_basic(data, media_type)
        
        directors, cast = [], []
        credits_obj = self._get_attr(data, 'credits')
        if credits_obj:
            directors, cast = self._parse_credits(credits_obj)

        recommendations = []
        recs_obj = self._get_attr(data, 'recommendations')
        if recs_obj:
            recs_list = self._ensure_list(self._get_attr(recs_obj, 'results'))
            recommendations = [self._parse_basic(i, media_type) for i in recs_list[:10]]
            
        similar = []
        sim_obj = self._get_attr(data, 'similar')
        if sim_obj:
            sim_list = self._ensure_list(self._get_attr(sim_obj, 'results'))
            similar = [self._parse_basic(i, media_type) for i in sim_list[:10]]

        genres = []
        raw_genres = self._ensure_list(self._get_attr(data, 'genres'))
        genre_ids = []
        for g in raw_genres:
            gid = self._get_attr(g, 'id')
            gname = self._get_attr(g, 'name')
            genres.append(Genre(id=gid, name=gname))
            genre_ids.append(gid)
        
        seasons = []
        if media_type == 'tv':
            raw_seasons = self._ensure_list(self._get_attr(data, 'seasons'))
            for s in raw_seasons:
                seasons.append(Season(
                    id=self._get_attr(s, 'id', 0),
                    season_number=self._get_attr(s, 'season_number', 0),
                    name=self._get_attr(s, 'name', ''),
                    poster_path=self._get_image_url(self._get_attr(s, 'poster_path')),
                    episode_count=self._get_attr(s, 'episode_count', 0),
                    air_date=self._get_attr(s, 'air_date')
                ))

        basic.genre_ids = genre_ids 

        return MediaDetail(
            **basic.dict(),
            genres=genres,
            tagline=self._get_attr(data, 'tagline', ''),
            status=self._get_attr(data, 'status', ''),
            directors=directors,
            cast=cast,
            recommendations=recommendations,
            similar=similar,
            seasons=seasons
        )

    def search_media(self, query: str, page: int = 1) -> SearchResult:
        results = self.search_api.multi(term=query, page=page)
        safe_results = self._ensure_list(results)
        
        parsed = []
        for item in safe_results:
            m_type = self._get_attr(item, 'media_type')
            if m_type not in ['movie', 'tv']: continue

            parsed.append(self._parse_basic(item))
            
        return SearchResult(total_results=len(parsed), page=page, results=parsed)

    def discover_media(self, media_type: str, page: int = 1, sort_by: str = "popularity.desc",
                       with_genres: Optional[str] = None, start_date: Optional[str] = None,
                       end_date: Optional[str] = None, min_vote: float = 0, min_vote_count: int = 0) -> SearchResult:
        params = {
            'page': page, 
            'sort_by': sort_by, 
            'vote_average.gte': min_vote, 
            'vote_count.gte': min_vote_count,
            'language': settings.TMDB_LANGUAGE
        }
        if with_genres: params['with_genres'] = with_genres

        if media_type == 'movie':
            if start_date: params['primary_release_date.gte'] = start_date
            if end_date: params['primary_release_date.lte'] = end_date
            results = self.discover_api.discover_movies(params)
        elif media_type == 'tv':
            if start_date: params['first_air_date.gte'] = start_date
            if end_date: params['first_air_date.lte'] = end_date
            results = self.discover_api.discover_tv_shows(params)
        else:
            results = []

        parsed = [self._parse_basic(item, media_type) for item in self._ensure_list(results)]
        return SearchResult(total_results=len(parsed), page=page, results=parsed)

    def get_discovery(self, list_type: str, page: int = 1) -> SearchResult:
        if list_type == 'movies_playing':
            res = self.movie_api.now_playing(page=page)
            m_type = 'movie'
        elif list_type == 'tv_airing':
            res = self.tv_api.on_the_air(page=page)
            m_type = 'tv'
        else:
            res = []
            m_type = 'movie'

        parsed = [self._parse_basic(item, m_type) for item in self._ensure_list(res)]
        return SearchResult(total_results=len(parsed), page=page, results=parsed)

    def get_genres(self, media_type: str):
        if media_type == 'movie':
            return self._ensure_list(self.genre_api.movie_list())
        return self._ensure_list(self.genre_api.tv_list())

    def get_season_details(self, tv_id: int, season_number: int) -> Season:
        s_data = self.season_api.details(tv_id, season_number)
        
        episodes = []
        raw_eps = self._ensure_list(self._get_attr(s_data, 'episodes'))
        
        for ep in raw_eps:
            episodes.append(Episode(
                id=self._get_attr(ep, 'id'),
                episode_number=self._get_attr(ep, 'episode_number'),
                season_number=season_number,
                name=self._get_attr(ep, 'name'),
                overview=self._get_attr(ep, 'overview'),
                still_path=self._get_image_url(self._get_attr(ep, 'still_path'), "original"),
                air_date=self._get_attr(ep, 'air_date'),
                vote_average=self._get_attr(ep, 'vote_average', 0.0)
            ))

        return Season(
            id=self._get_attr(s_data, 'id', 0) or 0,
            season_number=season_number,
            name=self._get_attr(s_data, 'name', f"Season {season_number}"),
            poster_path=self._get_image_url(self._get_attr(s_data, 'poster_path')),
            episode_count=len(episodes),
            air_date=self._get_attr(s_data, 'air_date'),
            episodes=episodes
        )

tmdb_service = TMDBService()