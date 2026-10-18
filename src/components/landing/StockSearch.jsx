import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Search, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { mockStocks } from "@/data/mockStocks";
import { isValidTicker, normalizeTicker } from "@/lib/format";
import { useDataMode } from "@/context/dataMode";
import { searchStocks } from "@/services/api";
import { securityLabel, stockLocation } from "@/lib/securityIdentity";

export default function StockSearch({ compact = false, dashboard = false }) {
  const id = useId();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [offset, setOffset] = useState(0);
  const inputRef = useRef(null);
  const { mode } = useDataMode();
  const [providerSearch, setProviderSearch] = useState({
    query: "",
    results: [],
    status: "idle",
  });
  const query = normalizeTicker(value);
  const demoSuggestions = mockStocks.filter(
    (stock) =>
      stock.ticker.includes(query) || stock.name.toUpperCase().includes(query),
  );
  const suggestions =
    mode === "provider"
      ? providerSearch.query === query
        ? providerSearch.results
        : []
      : demoSuggestions;
  const providerLoading =
    mode === "provider" &&
    !!query &&
    (providerSearch.query !== query || providerSearch.status === "loading");
  useEffect(() => {
    if (mode !== "provider" || !query) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setProviderSearch((previous) => ({ query, status: "loading", results: offset && previous.query === query ? previous.results : [] }));
      searchStocks(query, { signal: controller.signal, limit: 10, offset })
        .then((response) => {
          if (!controller.signal.aborted)
            setProviderSearch({
              query,
              status: "ready",
              results: [...new Map((response.results ?? []).map((stock) => [stock.listing_id ?? stock.instrument_id ?? `${stock.ticker}:${stock.exchange ?? ""}`, stock])).values()],
              warnings: response.warnings ?? [],
              providerStatus: response.status,
              hasMore: response.has_more === true,
              asOf: response.as_of,
            });
        })
        .catch((requestError) => {
          if (!controller.signal.aborted)
            setProviderSearch({
              query,
              status: "error",
              results: [],
              error: requestError.message,
            });
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [mode, query, offset]);

  function choose(stock) {
    navigate(stockLocation(stock));
    setOpen(false);
  }
  function changePage(delta) {
    setActive(-1);
    setOffset((previous) => Math.max(0, previous + delta));
    inputRef.current?.focus();
    setOpen(true);
  }
  function submit(event) {
    event.preventDefault();
    if (open && active >= 0 && suggestions[active]) {
      choose(suggestions[active]);
      return;
    }
    const matches = (mode === "provider" ? suggestions : mockStocks).filter(
      (stock) => stock.name.toUpperCase() === query || stock.ticker.toUpperCase() === query,
    );
    if (matches.length > 1 || (mode === "provider" && matches.length === 1 && providerSearch.hasMore)) {
      setError("Several securities match. Choose the exchange and share class from the suggestions.");
      setOpen(true);
      return;
    }
    if (matches.length === 1) {
      choose(matches[0]);
      return;
    }
    if (!query) {
      setError("Enter a company name or ticker to get started.");
      inputRef.current?.focus();
      return;
    }
    if (!isValidTicker(query, mode === "provider")) {
      setError(
        mode === "provider" ? "Enter a valid listing symbol or choose a company from the suggestions (for example, BRK.B)." : "Use 1–5 letters, with an optional share class (for example, BRK.B).",
      );
      setOpen(false);
      inputRef.current?.focus();
      return;
    }
    choose(query);
  }
  function onKeyDown(event) {
    if (event.key === "Escape") {
      setOpen(false);
      setActive(-1);
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActive((previous) =>
        event.key === "ArrowDown"
          ? Math.min(previous + 1, suggestions.length - 1)
          : Math.max(previous - 1, 0),
      );
    }
  }

  return (
    <div
      className={`stock-search ${compact ? "stock-search-compact" : ""} ${dashboard ? "dashboard-search" : ""}`}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setOpen(false);
          setActive(-1);
        }
      }}
    >
      <form onSubmit={submit} noValidate>
        <label htmlFor={id} className="sr-only">
          Search by company or ticker
        </label>
        <div className={`search-field ${error ? "search-field-error" : ""}`}>
          <Search size={19} aria-hidden="true" />
          <Input
            ref={inputRef}
            id={id}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={open && suggestions.length > 0}
            aria-controls={`${id}-suggestions`}
            aria-activedescendant={
              active >= 0 && open && suggestions[active]
                ? `${id}-option-${active}`
                : undefined
            }
            aria-invalid={!!error}
            aria-describedby={`${id}-help${error ? ` ${id}-error` : ""}`}
            autoComplete="off"
            spellCheck={false}
            placeholder={
              dashboard
                ? "Search company or ticker"
                : "Search by company or ticker (e.g. AAPL, NVDA, MSFT)"
            }
            value={value}
            onChange={(event) => {
              setValue(event.target.value.toUpperCase());
              setError("");
              setOpen(true);
              setActive(-1);
              setOffset(0);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
          />
          <button
            className="search-submit"
            type="submit"
            aria-label="Search stock"
          >
            <ArrowRight size={18} />
          </button>
        </div>
        {open && suggestions.length > 0 && (
          <div className="search-results">
          <ul
            id={`${id}-suggestions`}
            role="listbox"
            aria-label={
              mode === "provider"
                ? "Provider stock suggestions"
                : "Demo stock suggestions"
            }
            className="search-suggestions"
          >
            {suggestions.map((stock, index) => (
              <li
                id={`${id}-option-${index}`}
                key={stock.listing_id ?? stock.instrument_id ?? `${stock.ticker}:${stock.exchange ?? ""}`}
                role="option"
                aria-selected={active === index}
                className={active === index ? "suggestion-active" : ""}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(stock)}
              >
                <span className="suggestion-ticker">{stock.ticker}</span>
                <span className="suggestion-company"><span>{stock.name}</span>{mode === "provider" && <small>{[stock.exchange || "Exchange unverified", securityLabel(stock.instrument_type), stock.share_class && `Class ${stock.share_class}`, stock.listing_status && stock.listing_status !== "active" && stock.listing_status.replaceAll("_", " ")].filter(Boolean).join(" · ")}</small>}</span>
                <ArrowRight size={14} aria-hidden="true" />
              </li>
            ))}
          </ul>
          {mode === "provider" && offset > 0 && providerSearch.status === "ready" && <button className="search-more" type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => changePage(-10)}>Previous matching securities</button>}
          {mode === "provider" && providerSearch.query === query && providerSearch.hasMore && providerSearch.status === "ready" && <button className="search-more" type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => changePage(10)}>Show more matching securities</button>}
          </div>
        )}
        {error && (
          <p role="alert" id={`${id}-error`} className="search-error">
            {error}
          </p>
        )}
        {open && providerLoading && (
          <p role="status" className="search-help">
            Searching the security registry…
          </p>
        )}
        {open &&
          mode === "provider" &&
          providerSearch.query === query &&
          providerSearch.status === "error" && (
            <p role="alert" className="search-error">
              {providerSearch.error} No demo suggestions have been substituted.
            </p>
          )}
        {open &&
          mode === "provider" &&
          providerSearch.query === query &&
          providerSearch.status === "ready" &&
          (providerSearch.providerStatus === "stale" ||
            providerSearch.warnings.length > 0) && (
            <p role="status" className="search-help">
              Company directory status:{" "}
              {providerSearch.providerStatus || "partial"}.{" "}
              {providerSearch.warnings
                .map((warning) => warning.message)
                .join(" ")}
            </p>
          )}
        {open &&
          mode === "provider" &&
          providerSearch.query === query &&
          providerSearch.status === "ready" &&
          !suggestions.length &&
          query && (
            <p role="status" className="search-help">
              No matching securities in the available registry. A listing may be unavailable or unverified.
            </p>
          )}
      </form>
      {!compact && (
        <div className="popular-stocks">
          <span>Popular</span>
          {["AAPL", "MSFT", "NVDA", "AMZN"].map((ticker) => (
            <button key={ticker} onClick={() => choose(ticker)}>
              {ticker}
              <ArrowUpSmall />
            </button>
          ))}
        </div>
      )}
      <p id={`${id}-help`} className={dashboard ? "sr-only" : "search-help"}>
        {dashboard
          ? mode === "provider"
            ? "Search the security registry. Exchange, instrument and evidence coverage are checked separately."
            : "Search the 10 fictional company datasets. No live market data."
          : mode === "provider" ? "Search the security registry. Search coverage does not guarantee an available valuation." : "Explore fictional demonstration datasets. Switch to provider data in the dashboard for verified source coverage."}
      </p>
    </div>
  );
}

function ArrowUpSmall() {
  return <span aria-hidden="true">↗</span>;
}
