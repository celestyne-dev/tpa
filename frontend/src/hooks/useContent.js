import { useCallback, useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  fetchArticle,
  fetchArticles,
  selectArticle,
  selectArticleList,
} from "@/store/slices/articlesSlice";
import { fetchPage, selectPage } from "@/store/slices/pagesSlice";
import {
  fetchCollection,
  fetchProduct,
  fetchProducts,
  selectCollection,
  selectProduct,
  selectProducts,
} from "@/store/slices/productsSlice";
import { fetchSite, selectSite } from "@/store/slices/siteSlice";
import { fetchTopic, fetchTopics, selectTopic, selectTopicList } from "@/store/slices/topicsSlice";
import { Status } from "@/store/status";

const idle = { status: Status.idle, error: null };

/** Normalises a store entry into { data, status, error, isLoading, isError, isNotFound, retry }. */
function useResource(entry, load, deps, pickData) {
  const dispatch = useDispatch();
  useEffect(() => {
    dispatch(load());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  const retry = useCallback(() => dispatch(load(true)), [dispatch, load]);
  const state = entry ?? idle;
  return {
    data: state.status === Status.succeeded ? pickData(state) : null,
    status: state.status,
    error: state.error,
    isLoading: state.status === Status.idle || state.status === Status.loading,
    isError: state.status === Status.failed,
    isNotFound: state.status === Status.failed && state.error?.status === 404,
    retry,
  };
}

export function useSite() {
  const entry = useSelector(selectSite);
  const load = useCallback((force) => fetchSite({ force }), []);
  return useResource(entry, load, [load], (s) => s.data);
}

export function useTopics() {
  const entry = useSelector(selectTopicList);
  const load = useCallback((force) => fetchTopics({ force }), []);
  return useResource(entry, load, [load], (s) => s.items);
}

export function useTopic(slug) {
  const entry = useSelector(selectTopic(slug));
  const load = useCallback((force) => fetchTopic({ slug, force }), [slug]);
  return useResource(entry, load, [load], (s) => s.data);
}

export function useArticles({ topic, featured, page = 1, pageSize = 12 } = {}) {
  const query = { topic, featured, page, pageSize };
  const entry = useSelector(selectArticleList(query));
  const load = useCallback(
    (force) => fetchArticles({ topic, featured, page, pageSize, force }),
    [topic, featured, page, pageSize],
  );
  const result = useResource(entry, load, [load], (s) => s.items);
  return { ...result, pagination: entry?.pagination ?? null };
}

export function useArticle(slug) {
  const entry = useSelector(selectArticle(slug));
  const load = useCallback((force) => fetchArticle({ slug, force }), [slug]);
  return useResource(entry, load, [load], (s) => ({ article: s.article, related: s.related }));
}

export function useProducts() {
  const entry = useSelector(selectProducts);
  const load = useCallback((force) => fetchProducts({ force }), []);
  const result = useResource(entry, load, [load], (s) => s.items);
  return { ...result, meta: entry?.meta ?? {} };
}

/** One published product (detail page). */
export function useProduct(slug) {
  const entry = useSelector(selectProduct(slug));
  const load = useCallback((force) => fetchProduct({ slug, force }), [slug]);
  return useResource(entry, load, [load], (s) => s.data);
}

export function useCollection(slug) {
  const entry = useSelector(selectCollection(slug));
  const load = useCallback((force) => fetchCollection({ slug, force }), [slug]);
  return useResource(entry, load, [load], (s) => s.data);
}

/** A published CMS page by path (resolved sections; drafts are never returned). */
export function usePage(path) {
  const entry = useSelector(selectPage(path));
  const load = useCallback((force) => fetchPage({ path, force }), [path]);
  return useResource(entry, load, [load], (s) => s.data);
}
