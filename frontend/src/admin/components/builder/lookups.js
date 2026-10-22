import { createContext, useContext } from "react";

/** Picker data shared by every field of a builder screen (articles, topics, CTAs, links ...). */
export const BuilderLookupsContext = createContext({
  options: { articles: [], topics: [], authors: [] },
  ctas: [],
  shared: [],
  links: [],
  reload: () => {},
});
export const useBuilderLookups = () => useContext(BuilderLookupsContext);
