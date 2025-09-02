import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": "/src",
            "@/components": "/src/components",
            "@/hooks": "/src/hooks",
            "@/api": "/src/api",
            "@/utils": "/src/utils",
            "@/types": "/src/types",
            "@/constants": "/src/constants"
        }
    },
    optimizeDeps: {
        esbuildOptions: {
            target: "esnext"
        }
    },
    build: {
        outDir: "../backend/static",
        emptyOutDir: true,
        sourcemap: true,
        target: "esnext",
        rollupOptions: {
            output: {
                manualChunks: {
                    vendor: ["react", "react-dom"],
                    fluent: ["@fluentui/react-components", "@fluentui/react-icons"],
                    monaco: ["@monaco-editor/react"]
                }
            }
        }
    },
    server: {
        proxy: {
            "/chat": {
                target: "http://localhost:5000"
            },
            "/list_indexes": {
                target: "http://localhost:5000"
            },
            "/get_citation_doc": {
                target: "http://localhost:5000"
            },
            "/upload": {
                target: "http://localhost:5000"
            },
            "/upload_status": {
                target: "http://localhost:5000"
            },
            "/process_document": {
                target: "http://localhost:5000"
            },
            "/delete_index": {
                target: "http://localhost:5000"
            },
            "/api/delete_index": {
                target: "http://localhost:5000"
            },
            "/api/admin": {
                target: "http://localhost:5000"
            }
        }
    }
});
