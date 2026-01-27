const { createApp, ref, computed, onMounted, onUnmounted, watch, nextTick, defineComponent } = Vue;

// --- Utility: Format Bytes ---
const formatBytes = (bytes, decimals = 2) => {
    if (bytes === null || bytes === undefined) return '';
    // 修正：如果 bytes 已经是包含单位的字符串（如 "77 GB"），则直接返回，不再解析
    if (typeof bytes === 'string' && /[a-zA-Z]/.test(bytes)) return bytes;
    
    const parsed = parseInt(bytes);
    if (isNaN(parsed)) return bytes || ''; 
    if (parsed === 0) return '0 B';
    
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(parsed) / Math.log(k));
    return `${parseFloat((parsed / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
};

// --- Component: Tree Node (For 115) ---
const TreeNode = defineComponent({
    name: 'TreeNode',
    template: '#tree-node-template',
    props: {
        item: Object, 
        shareLink: String,
        password: { type: String, default: '' },
        isRoot: { type: Boolean, default: false },
        folderNameTemplate: { type: String, default: '' }
    },
    emits: ['notify'],
    setup(props, { emit }) {
        const isOpen = ref(false);
        const loading = ref(false);
        const children = ref([]);

        const isISO = computed(() => {
            return props.item.name && props.item.name.toLowerCase().endsWith('.iso');
        });

        const shouldCreateFolder = computed(() => {
            return isISO.value && props.folderNameTemplate;
        });

        const saveButtonTitle = computed(() => {
            if (shouldCreateFolder.value) {
                return `转存并整理到: ${props.folderNameTemplate}`;
            }
            return '转存到网盘';
        });

        const toggle = async () => {
            if (props.item.is_dir && !isISO.value) {
                if (isOpen.value) {
                    isOpen.value = false;
                } else {
                    isOpen.value = true;
                    if (children.value.length === 0) {
                        await fetchChildren();
                    }
                }
            }
        };

        const fetchChildren = async () => {
            loading.value = true;
            try {
                const res = await fetch('/p115/share/list', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        share_link: props.shareLink,
                        cid: props.item.id,
                        password: props.password
                    })
                });
                const json = await res.json();
                if (json.state) {
                    let list = json.data.list;
                    
                    // 智能展平逻辑
                    if (props.isRoot && list.length === 1 && list[0].is_dir) {
                        const subRes = await fetch('/p115/share/list', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                share_link: props.shareLink,
                                cid: list[0].id, 
                                password: props.password
                            })
                        });
                        const subJson = await subRes.json();
                        if (subJson.state) {
                            list = subJson.data.list;
                        }
                    }
                    children.value = list;
                } else {
                    emit('notify', { message: '加载目录失败: ' + json.message, type: 'error' });
                    isOpen.value = false;
                }
            } catch (e) {
                emit('notify', { message: '网络请求错误', type: 'error' });
                isOpen.value = false;
            } finally {
                loading.value = false;
            }
        };

        const onSave = async () => {
            try {
                let msg = '正在提交转存任务...';
                if (shouldCreateFolder.value) {
                    msg = `正在创建文件夹 "${props.folderNameTemplate}" 并转存...`;
                }
                emit('notify', { message: msg, type: 'success' }); 
                
                const payload = {
                    share_link: props.shareLink,
                    file_ids: [props.item.id],
                    password: props.password,
                    new_directory_name: shouldCreateFolder.value ? props.folderNameTemplate : null
                };

                const res = await fetch('/p115/share/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const json = await res.json();
                if (json.state) {
                    emit('notify', { message: '转存成功: ' + props.item.name, type: 'success' });
                } else {
                    emit('notify', { message: '转存失败: ' + json.message, type: 'error' });
                }
            } catch (e) {
                emit('notify', { message: '请求失败: ' + e.message, type: 'error' });
            }
        };

        return { isOpen, loading, children, toggle, onSave, isISO, formatBytes, saveButtonTitle };
    }
});

const CACHE_TTL = 8 * 60 * 60 * 1000;
const cache = {
    get(key) {
        try {
            const item = localStorage.getItem(key);
            if (!item) return null;
            const parsed = JSON.parse(item);
            if (Date.now() - parsed.ts > CACHE_TTL) { localStorage.removeItem(key); return null; }
            return parsed.data;
        } catch (e) { return null; }
    },
    set(key, data) {
        try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data: data })); } catch (e) {}
    }
};
const fetchWithCache = async (url) => {
    const cacheKey = `fullbr_v6_${url}`;
    const cached = cache.get(cacheKey);
    if (cached) return cached;
    const res = await fetch(url);
    if (!res.ok) throw new Error("API Error");
    const json = await res.json();
    cache.set(cacheKey, json);
    return json;
};

// Helper: Parse Size for Sorting
const parseSize = (str) => {
    if (!str || typeof str !== 'string') return 0;
    const units = { 'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4, 'PB': 1024**5 };
    const match = str.match(/([\d.]+)\s*([a-zA-Z]+)/);
    if (!match) return 0;
    const val = parseFloat(match[1]);
    const unit = match[2].toUpperCase();
    return val * (units[unit] || 1);
};

const ResourcePanel = {
    template: '#resource-panel-template',
    components: { TreeNode },
    props: ['tmdbId', 'mediaType', 'seasonNumber', 'episodeNumber', 'availability', 'context', 'injected115', 'mediaInfo'],
    emits: ['notify'],
    setup(props, { emit }) {
        const activeTab = ref('');
        const localResources = ref([]);
        const loading = ref(false);

        const isoFolderName = computed(() => {
            if (!props.mediaInfo || !props.mediaInfo.title) return '';
            const { title, date, tmdb_id } = props.mediaInfo;
            const year = date ? date.split('-')[0] : '';
            
            if (year) {
                return `${title} (${year}) {tmdbid-${tmdb_id}}`;
            }
            return `${title} {tmdbid-${tmdb_id}}`;
        });

        const tabs = computed(() => {
            const t = [];
            if ((props.injected115 && props.injected115.length > 0) || 
                (props.mediaType === 'movie' && props.availability?.has_115)) {
                t.push({ id: '115_share', label: '115分享', icon: 'fa-solid fa-cloud' });
            }
            const hasLocalMagnet = localResources.value.some(r => r.link_type === 'magnet');
            if (hasLocalMagnet || (props.mediaType === 'movie' && props.availability?.has_magnet)) {
                t.push({ id: 'magnet', label: '磁力链', icon: 'fa-solid fa-magnet' });
            }
            const hasLocalEd2k = localResources.value.some(r => r.link_type === 'ed2k');
            if (hasLocalEd2k || (props.mediaType === 'movie' && props.availability?.has_ed2k)) {
                t.push({ id: 'ed2k', label: '电驴/Ed2k', icon: 'fa-solid fa-network-wired' });
            }
            return t;
        });

        // Sorted Display Resources
        const displayResources = computed(() => {
            let list = [];
            if (props.mediaType === 'tv_episode') {
                list = [...localResources.value];
            } else if (activeTab.value === '115_share' && props.mediaType !== 'movie') {
                list = [...(props.injected115 || [])];
            } else {
                list = localResources.value.filter(r => r.link_type === activeTab.value);
            }
            // Sort by Size Descending
            return list.sort((a, b) => parseSize(b.size) - parseSize(a.size));
        });

        const isIso = (res) => (res.title || res.name || '').toLowerCase().endsWith('.iso');
        const copyLink = (link) => navigator.clipboard.writeText(link).then(() => emit('notify', {message: '链接已复制', type:'success'})).catch(() => emit('notify', {message: '复制失败', type:'error'}));

        const addOfflineTask = async (url) => {
            if (!url) return;
            emit('notify', { message: '正在添加离线任务...', type: 'success' });
            try {
                const res = await fetch('/p115/offline/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ urls: [url] })
                });
                const json = await res.json();
                if (json.state) {
                    emit('notify', { message: '离线任务添加成功', type: 'success' });
                } else {
                    emit('notify', { message: '任务添加失败: ' + json.message, type: 'error' });
                }
            } catch (e) {
                emit('notify', { message: '请求失败: ' + e.message, type: 'error' });
            }
        };

        const fetchLocalData = async () => {
            loading.value = true;
            localResources.value = [];
            try {
                let url = '';
                if (props.mediaType === 'movie') {
                    const params = new URLSearchParams();
                    if(activeTab.value) params.append('source_type', activeTab.value);
                    url = `/resources/movie/${props.tmdbId}?${params.toString()}`;
                    const data = await fetchWithCache(url);
                    localResources.value = data; 
                } else if (props.mediaType === 'tv_season') {
                    url = `/resources/tv/${props.tmdbId}/season/${props.seasonNumber}`;
                    const data = await fetchWithCache(url);
                    localResources.value = data;
                } else if (props.mediaType === 'tv_episode') {
                    url = `/resources/tv/${props.tmdbId}/season/${props.seasonNumber}/episode/${props.episodeNumber}`;
                    const data = await fetchWithCache(url);
                    localResources.value = data;
                }
            } catch (e) { console.error(e); } 
            finally { loading.value = false; }
        };

        const updateActiveTab = () => {
            if (props.mediaType === 'tv_episode') return;
            const currentExists = tabs.value.find(t => t.id === activeTab.value);
            if (currentExists) return;
            if (tabs.value.length > 0) activeTab.value = tabs.value[0].id;
            else activeTab.value = '';
        };

        watch([() => props.injected115, localResources], () => updateActiveTab());
        watch(activeTab, () => { if (props.mediaType === 'movie') fetchLocalData(); });
        watch(() => [props.seasonNumber, props.episodeNumber], () => { localResources.value = []; fetchLocalData(); });

        onMounted(() => {
            if (props.mediaType === 'movie' && props.availability) {
                if (props.availability.has_115) activeTab.value = '115_share';
                else if (props.availability.has_magnet) activeTab.value = 'magnet';
                else activeTab.value = 'ed2k';
                fetchLocalData();
            } else {
                fetchLocalData().then(() => updateActiveTab());
            }
        });

        return { activeTab, displayResources, tabs, loading, copyLink, isIso, addOfflineTask, isoFolderName };
    }
};

createApp({
    components: { 'resource-panel': ResourcePanel },
    setup() {
        const currentView = ref('home');
        const isDark = ref(true);
        const showMobileSearch = ref(false);
        const loading = ref(false);
        const mediaType = ref('movie');
        const mediaList = ref([]);
        const genres = ref([]);
        const allGenresMap = ref({}); 
        const searchQuery = ref('');
        const currentPage = ref(1);
        const hasMore = ref(true);
        const loadTrigger = ref(null);
        const showSearchTrending = ref(false);
        const detailData = ref(null);
        const trendingList = ref([]);
        const trendingLoading = ref(false);
        const trendingTimeWindow = ref('week');
        const trendingContainer = ref(null);

        const selectedSeasonNumber = ref(null);
        const currentSeasonData = ref(null);
        const raw115Resources = ref([]);
        
        const isDragging = ref(false);
        const startX = ref(0);
        const scrollLeft = ref(0);
        const isDragMove = ref(false);

        const seasonTabsContainer = ref(null);
        const seasonTabsRefs = ref({});

        const showAdvancedFilters = ref(false);
        const filters = ref({ sortBy: 'popularity.desc', minVote: 0, minVoteCount: 500, selectedGenres: [], dateRange: null, originalLanguage: null });
        const showEpisodeModal = ref(false);
        const currentEpisode = ref({});

        const subscriptionList = ref([]);
        const showSubscribeModal = ref(false);
        const subForm = ref({ season_number: 1, start_episode: 1 });

        const toasts = ref([]);
        let toastIdCounter = 0;

        let autoPlayInterval = null;

        const dateRanges = computed(() => {
            const ranges = [];
            ranges.push({ label: '1950前', start: '1900-01-01', end: '1949-12-31' });
            ranges.push({ label: '50s-60s', start: '1950-01-01', end: '1969-12-31' });
            ranges.push({ label: '70s-80s', start: '1970-01-01', end: '1989-12-31' });
            ranges.push({ label: '90s', start: '1990-01-01', end: '1999-12-31' });
            ranges.push({ label: '2000s', start: '2000-01-01', end: '2009-12-31' });
            ranges.push({ label: '2010s', start: '2010-01-01', end: '2019-12-31' });
            for (let y = 2020; y <= new Date().getFullYear(); y++) {
                ranges.push({ label: `${y}`, start: `${y}-01-01`, end: `${y}-12-31` });
            }
            return ranges.reverse();
        });
        
        const sortOptions = [
            { label: '最热门', value: 'popularity.desc', icon: 'fa-solid fa-fire' },
            { label: '最高评分', value: 'vote_average.desc', icon: 'fa-solid fa-star' },
            { label: '最新上映', value: 'primary_release_date.desc', icon: 'fa-solid fa-calendar-days' }
        ];

        const languageOptions = [
            { label: '华语', code: 'zh' },
            { label: '英语', code: 'en' },
            { label: '日本', code: 'ja' },
            { label: '韩国', code: 'ko' },
            { label: '法国', code: 'fr' },
            { label: '德国', code: 'de' },
            { label: '西班牙', code: 'es' },
            { label: '泰国', code: 'th' },
            { label: '印度', code: 'hi' },
            { label: '俄罗斯', code: 'ru' }
        ];

        const toggleLanguage = (code) => {
            if (filters.value.originalLanguage === code) {

                filters.value.originalLanguage = null;
                filters.value.minVoteCount = 500;
            } else {
                filters.value.originalLanguage = code;
                
                if (code === 'en') {
                    filters.value.minVoteCount = 500;
                } else {
                    filters.value.minVoteCount = 50;
                }
            }
            currentPage.value = 1;
            refreshData();
        };

        const showToast = ({ message, type = 'success', duration = 3000 }) => {
            const id = toastIdCounter++;
            toasts.value.push({ id, message, type });
            setTimeout(() => removeToast(id), duration);
        };

        const removeToast = (id) => {
            const idx = toasts.value.findIndex(t => t.id === id);
            if (idx !== -1) toasts.value.splice(idx, 1);
        };

        const toggleTheme = () => {
            isDark.value = !isDark.value;
            if (isDark.value) document.documentElement.classList.add('dark');
            else document.documentElement.classList.remove('dark');
        };

        const loadGenres = async () => {
             try { const data = await fetchWithCache(`/tmdb/genres/${mediaType.value}`); genres.value = data; } catch (e) {}
        };

        const loadAllGenres = async () => {
            try {
                const [movies, tvs] = await Promise.all([
                    fetchWithCache('/tmdb/genres/movie'),
                    fetchWithCache('/tmdb/genres/tv')
                ]);
                const map = {};
                if(movies) movies.forEach(g => map[g.id] = g.name);
                if(tvs) tvs.forEach(g => map[g.id] = g.name);
                allGenresMap.value = map;
            } catch(e) {}
        };

        const getGenreNames = (ids) => {
            if(!ids || !ids.length) return [];
            return ids.map(id => allGenresMap.value[id] || genres.value.find(g => g.id === id)?.name).filter(Boolean).slice(0, 3);
        };

        const buildQueryUrl = (base) => {
            const params = new URLSearchParams();
            params.append('page', currentPage.value);
            if (currentView.value === 'home') {
                params.append('sort_by', filters.value.sortBy);
                params.append('min_vote', filters.value.minVote);
                params.append('min_vote_count', filters.value.minVoteCount);
                if (filters.value.selectedGenres.length) params.append('with_genres', filters.value.selectedGenres.join(','));
                if (filters.value.originalLanguage) params.append('with_original_language', filters.value.originalLanguage);
                if (filters.value.dateRange) { params.append('start_date', filters.value.dateRange.start); params.append('end_date', filters.value.dateRange.end); }
            } else if (currentView.value === 'search') { params.append('query', searchQuery.value); }
            return `${base}?${params.toString()}`;
        };

        const handleSearchBlur = () => {
            setTimeout(() => {
                showSearchTrending.value = false;
            }, 200);
        };

        const isSubscribed = computed(() => {
            if (!detailData.value || !subscriptionList.value) return false;
            return subscriptionList.value.some(s => 
                s.tmdb_id === detailData.value.tmdb_id && 
                s.media_type === detailData.value.media_type
            );
        });

        const toggleSubscribe = async () => {
            if (isSubscribed.value) {
                const subs = subscriptionList.value.filter(s => 
                    s.tmdb_id === detailData.value.tmdb_id && 
                    s.media_type === detailData.value.media_type
                );
                
                const confirmMsg = subs.length > 1 
                    ? '确定要取消该剧集的所有订阅吗？' 
                    : '确定要取消订阅吗？';

                if(confirm(confirmMsg)) {
                    try {
                        for (const sub of subs) {
                            await fetch(`/subscribe/${sub.id}`, { method: 'DELETE' });
                        }
                        showToast({ message: '已取消订阅', type: 'success' });
                        await refreshSubscriptions();
                    } catch(e) {
                        showToast({ message: '取消失败', type: 'error' });
                    }
                }
            } else {
                openSubscribeModal();
            }
        };

        const refreshSubscriptions = async () => {
            try {
                const res = await fetch('/subscribe/list');
                if (res.ok) {
                    subscriptionList.value = await res.json();
                }
            } catch(e) {
                console.error("Failed to load subscriptions", e);
            }
        };

        const openSubscribeModal = () => {
            subForm.value = { 
                season_number: 1, 
                start_episode: 1 
            };
            
            if (detailData.value.media_type === 'tv') {
                if (selectedSeasonNumber.value) {
                    subForm.value.season_number = selectedSeasonNumber.value;
                } else if (detailData.value.seasons && detailData.value.seasons.length > 0) {
                    const first = detailData.value.seasons.find(s => s.season_number > 0) || detailData.value.seasons[0];
                    if (first) subForm.value.season_number = first.season_number;
                }
            }
            showSubscribeModal.value = true;
        };

        const submitSubscription = async () => {
            showSubscribeModal.value = false;
            
            try {
                showToast({ message: '正在提交订阅...', type: 'success' });
                
                const payload = {
                    tmdb_id: detailData.value.tmdb_id,
                    media_type: detailData.value.media_type,
                    title: detailData.value.title,
                    poster_path: detailData.value.poster_path,
                    season_number: subForm.value.season_number,
                    start_episode: subForm.value.start_episode
                };

                const res = await fetch('/subscribe/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const json = await res.json();
                
                if (res.ok) {
                    showToast({ message: json.message, type: 'success' });
                    await refreshSubscriptions();
                } else {
                    showToast({ message: '订阅失败: ' + json.detail, type: 'error' });
                }
            } catch(e) {
                showToast({ message: '请求错误: ' + e.message, type: 'error' });
            }
        };

        const deleteSubscription = async (id) => {
            if(!confirm('确定要取消订阅吗？')) return;
            try {
                const res = await fetch(`/subscribe/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    showToast({ message: '已取消订阅', type: 'success' });
                    refreshSubscriptions();
                }
            } catch(e) {
                showToast({ message: '操作失败', type: 'error' });
            }
        };

        const fetchTrending = async () => {
            trendingLoading.value = true;
            try {
                const url = `/tmdb/trending/all/${trendingTimeWindow.value}`;
                const data = await fetchWithCache(url);
                trendingList.value = data || [];
            } catch (e) {
                console.error("Fetch trending failed", e);
            } finally {
                trendingLoading.value = false;
            }
        };

        const switchTrendingWindow = (window) => {
            if (trendingTimeWindow.value === window) return;
            trendingTimeWindow.value = window;
            fetchTrending();
        };

        // --- Auto Play Logic ---
        const startAutoPlay = () => {
            stopAutoPlay();
            autoPlayInterval = setInterval(() => {
                if(isDragging.value || !trendingContainer.value) return;
                
                const container = trendingContainer.value;
                const w = container.offsetWidth;
                let nextScroll = container.scrollLeft + w;
                
                if (nextScroll >= container.scrollWidth - 10) {
                    nextScroll = 0;
                }
                
                container.scrollTo({ left: nextScroll, behavior: 'smooth' });
            }, 5000); 
        };

        const stopAutoPlay = () => {
            if (autoPlayInterval) clearInterval(autoPlayInterval);
        };

        const pauseAutoPlay = () => stopAutoPlay();
        const resumeAutoPlay = () => startAutoPlay();

        const startDrag = (e) => {
            isDragging.value = true;
            isDragMove.value = false;
            pauseAutoPlay(); 
            const slider = trendingContainer.value;
            startX.value = e.pageX - slider.offsetLeft;
            scrollLeft.value = slider.scrollLeft;
            slider.style.scrollSnapType = 'none';
        };

        const onDrag = (e) => {
            if (!isDragging.value) return;
            e.preventDefault();
            isDragMove.value = true; 
            const slider = trendingContainer.value;
            const x = e.pageX - slider.offsetLeft;
            const walk = (x - startX.value) * 1.5; 
            slider.scrollLeft = scrollLeft.value - walk;
        };

        const stopDrag = () => {
            if(isDragging.value) {
                isDragging.value = false;
                resumeAutoPlay(); 
                if(trendingContainer.value) {
                    trendingContainer.value.style.scrollSnapType = 'x mandatory';
                }
            }
        };

        const handleTrendClick = (e, id, type) => {
            if (isDragMove.value) {
                e.preventDefault();
                e.stopPropagation();
                isDragMove.value = false; 
            } else {
                goToDetail(id, type);
            }
        };

        const loadMediaData = async (append = false) => {
            if (loading.value) return; 
            if (append && !hasMore.value) return;

            loading.value = true;
            try {
                let url = currentView.value === 'search' && searchQuery.value 
                    ? buildQueryUrl('/tmdb/search') 
                    : buildQueryUrl(`/tmdb/discover/${mediaType.value}`);
                
                if (url.includes('search') && !searchQuery.value) {
                    loading.value = false;
                    return;
                }

                const res = await fetchWithCache(url);
                const newResults = res.results || [];
                
                if (newResults.length < 20) {
                    hasMore.value = false;
                }

                if (append) {
                    mediaList.value.push(...newResults);
                } else {
                    mediaList.value = newResults;
                }
            } catch(e) {
                console.error(e);
            } finally { 
                loading.value = false; 
            }
        };

        const refreshData = () => {
            currentPage.value = 1;
            hasMore.value = true;
            mediaList.value = [];
            loadMediaData(false);
        };

        const switchMediaType = (type) => { 
            mediaType.value = type; 
            currentPage.value = 1; 
            filters.value.selectedGenres = []; 
            
            if (type === 'movie') {
                filters.value.sortBy = 'popularity.desc';
            } else {
                filters.value.sortBy = 'primary_release_date.desc';
            }
            
            loadGenres(); 
            refreshData(); 
        };

        let observer = null;
        const toggleGenre = (id) => { const idx = filters.value.selectedGenres.indexOf(id); if (idx > -1) filters.value.selectedGenres.splice(idx, 1); else filters.value.selectedGenres.push(id); currentPage.value = 1; refreshData(); };
        const toggleDateRange = (range) => { if (filters.value.dateRange?.label === range.label) filters.value.dateRange = null; else filters.value.dateRange = range; currentPage.value = 1; refreshData(); };
        const performSearch = () => { if(!searchQuery.value) return; currentView.value = 'search'; currentPage.value = 1; showMobileSearch.value = false; refreshData(); };
        const goHome = () => { currentView.value = 'home'; searchQuery.value = ''; currentPage.value = 1; refreshData(); };
        const goBack = () => { currentView.value = searchQuery.value ? 'search' : 'home'; };

        const goToDetail = async (id, type) => {
            loading.value = true;
            detailData.value = null;
            currentSeasonData.value = null;
            selectedSeasonNumber.value = null;
            raw115Resources.value = [];
            seasonTabsRefs.value = {}; 
            refreshSubscriptions();

            try {
                const targetType = type || mediaType.value;
                const data = await fetchWithCache(`/tmdb/details/${targetType}/${id}`);
                detailData.value = data;
                currentView.value = 'detail';

                if (targetType === 'tv') {
                    fetchWithCache(`/resources/tv/${id}`).then(res => { raw115Resources.value = res || []; });
                    if (data.seasons?.length) {
                        const first = data.seasons.find(s => s.season_number === 1) || data.seasons[0];
                        selectSeason(first);
                    }
                }
            } catch(e) { console.error(e); } 
            finally { loading.value = false; }
        };

        const selectSeason = async (season) => {
            selectedSeasonNumber.value = season.season_number;
            currentSeasonData.value = null;
            
            await nextTick();
            const el = seasonTabsRefs.value[season.season_number];
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
            }

            try {
                const data = await fetchWithCache(`/tmdb/details/tv/${detailData.value.tmdb_id}/season/${season.season_number}`);
                currentSeasonData.value = data;
            } catch(e) {}
        };

        const fullSeries115 = computed(() => {
            if (!detailData.value || !detailData.value.seasons || raw115Resources.value.length === 0) return [];
            const validSeasons = detailData.value.seasons.filter(s => s.season_number > 0).map(s => `S${s.season_number}`);
            if (validSeasons.length === 0) return [];
            return raw115Resources.value.filter(res => {
                if (!res.season_list) return false;
                return validSeasons.every(s => res.season_list.includes(s));
            });
        });

        const getCurrentSeason115 = (seasonNum) => {
            if (raw115Resources.value.length === 0) return [];
            
            const fullSeriesLinks = new Set(fullSeries115.value.map(r => r.link));
            const targetS = `S${seasonNum}`;
            const validSeasonsCount = detailData.value.seasons.filter(s => s.season_number > 0).length;

            return raw115Resources.value.filter(res => {
                return res.season_list && res.season_list.includes(targetS) && !fullSeriesLinks.has(res.link);
            }).map(res => {
                const newRes = { ...res };
                const isFull = (newRes.season_list.length >= validSeasonsCount); 
                if (!isFull) {
                    const nums = newRes.season_list.map(s => parseInt(s.replace('S',''))).filter(n => !isNaN(n)).sort((a,b) => a-b);
                    if (nums.length > 0) {
                        const isContinuous = nums.every((val, i) => i === 0 || val === nums[i-1] + 1);
                        if (isContinuous && nums.length > 1) newRes.season_tag = `包含 S${nums[0]}-S${nums[nums.length-1]}`;
                        else if (nums.length === 1) newRes.season_tag = `仅包含 S${nums[0]}`;
                        else newRes.season_tag = `包含 ${newRes.season_list.join(',')}`;
                    }
                }
                return newRes;
            });
        };

        const openEpisodeModal = (seasonNum, episode) => {
            currentEpisode.value = { ...episode, season_number: seasonNum };
            showEpisodeModal.value = true;
        };
        const closeEpisodeModal = () => showEpisodeModal.value = false;

        onMounted(() => {
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                isDark.value = true;
                document.documentElement.classList.add('dark');
            } else { isDark.value = false; }
            
            loadGenres();
            loadAllGenres();
            refreshData();
            fetchTrending().then(() => startAutoPlay());
            
            observer = new IntersectionObserver((entries) => {
                if (entries[0].isIntersecting && !loading.value && hasMore.value && mediaList.value.length > 0) {
                    currentPage.value++;
                    loadMediaData(true); 
                }
            }, {
                rootMargin: '200px', 
                threshold: 0.1
            });

            if (loadTrigger.value) observer.observe(loadTrigger.value);
        });

        onUnmounted(() => {
            stopAutoPlay();
        });

        watch(loadTrigger, (el) => {
            if (el && observer) observer.observe(el);
        });

        return {
            currentView, isDark, toggleTheme, mediaType, switchMediaType, mediaList, loading,
            searchQuery, performSearch, goHome, goBack, currentPage, showSearchTrending, handleSearchBlur,
            filters, genres, dateRanges, sortOptions, hasMore, loadTrigger, refreshData, showAdvancedFilters, toggleGenre, toggleDateRange, languageOptions, toggleLanguage,
            goToDetail, detailData, trendingList, trendingLoading, switchTrendingWindow, trendingTimeWindow, trendingContainer, isDragging, startDrag, onDrag, stopDrag, handleTrendClick,
            selectedSeasonNumber, currentSeasonData, selectSeason,
            showEpisodeModal, openEpisodeModal, closeEpisodeModal, currentEpisode, showMobileSearch,
            subscriptionList, refreshSubscriptions, isSubscribed, toggleSubscribe,
            showSubscribeModal, openSubscribeModal, subForm, submitSubscription, deleteSubscription,
            fullSeries115, getCurrentSeason115,
            seasonTabsContainer, seasonTabsRefs,
            toasts, showToast, removeToast,
            getGenreNames, pauseAutoPlay, resumeAutoPlay
        };
    }
}).mount('#app');