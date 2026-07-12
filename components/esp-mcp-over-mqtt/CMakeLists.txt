idf_component_register(SRCS "mcp_server.c" "jsonrpc.c" "mcp.c"
                    REQUIRES "mqtt" "cjson"
                    INCLUDE_DIRS "include")
