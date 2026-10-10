import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { initAuth } from "./auth";
import "./index.css";

const queries = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: false } } });

await initAuth(); // reads /auth/config and completes an Entra sign-in redirect, if any

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queries}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
