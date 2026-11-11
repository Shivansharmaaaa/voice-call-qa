import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { useRoute } from "./router";
import { Overview } from "./pages/Overview";
import { CallPage, Calls } from "./pages/Calls";
import { Playground } from "./pages/Playground";
import { About, Agents, BenchmarkPage } from "./pages/Static";
import "./styles.css";

const NAV = [
  ["/", "Overview"],
  ["/calls", "Calls"],
  ["/playground", "Playground"],
  ["/agents", "Agent specs"],
  ["/benchmark", "Benchmark"],
  ["/about", "About"],
] as const;

function App() {
  const { path, params } = useRoute();
  let page;
  if (path === "/") page = <Overview />;
  else if (path === "/calls") page = <Calls params={params} />;
  else if (path.startsWith("/call/")) page = <CallPage id={decodeURIComponent(path.slice(6))} />;
  else if (path === "/playground") page = <Playground key={params.get("from") ?? ""} params={params} />;
  else if (path === "/agents") page = <Agents />;
  else if (path === "/benchmark") page = <BenchmarkPage />;
  else if (path === "/about") page = <About />;
  else page = <div className="page"><h1>Not found</h1><a href="#/">Go to the overview</a></div>;

  const active = (p: string) => (p === "/" ? path === "/" : path.startsWith(p));
  return (
    <>
      <header className="topbar">
        <a className="brand" href="#/">
          <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="currentColor" /><path d="M7 16h3l2-6 4 12 3-9 2 3h4" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
          Voice Call QA
        </a>
        <nav>
          {NAV.map(([p, label]) => (
            <a key={p} href={`#${p}`} className={active(p) ? "on" : ""}>{label}</a>
          ))}
        </nav>
      </header>
      <main>{page}</main>
      <footer className="foot muted small">
        Independent demo by Shivansh Sharma · synthetic data · not affiliated with any company ·{" "}
        <a href="https://github.com/Shivansharmaaaa/voice-call-qa" target="_blank" rel="noreferrer">GitHub</a>
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
