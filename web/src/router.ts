import { useEffect, useState } from "react";

export interface Route {
  path: string;
  params: URLSearchParams;
}

function parse(): Route {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  return { path: path || "/", params: new URLSearchParams(query) };
}

export function useRoute(): Route {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => {
      setRoute(parse());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function href(path: string, params?: Record<string, string | undefined>): string {
  const q = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString() : "";
  return `#${path}${q ? `?${q}` : ""}`;
}

export function go(path: string, params?: Record<string, string | undefined>) {
  window.location.hash = href(path, params).slice(1);
}
