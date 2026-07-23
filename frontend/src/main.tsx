import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "antd/dist/reset.css";
import "./styles.css";
import { OperatorWorkbench } from "./OperatorWorkbench";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider theme={{ token: { colorPrimary: "#155eef", borderRadius: 8 } }}>
      <QueryClientProvider client={queryClient}>
        <OperatorWorkbench />
      </QueryClientProvider>
    </ConfigProvider>
  </React.StrictMode>,
);
