# Memeooorr Agent - MirrorDB Interaction Flow (AFMDB 2.0)

This document describes how the Memeooorr agent interacts with the MirrorDB service using the new AFMDB 2.0 interface, primarily relying on Agent Attributes for data storage. This approach replaces the previous AFMDB 1.0 model which used dedicated tables like `Tweets` and `Interactions`.

## Core Concepts (AFMDB 2.0)

*   **Agent Type:** A category or classification for agents (e.g., "memeooorr"). Defined once centrally in MirrorDB.
*   **Attribute Definition:** A template defining a specific piece of data that can be associated with an agent (e.g., "twitter\_username", "twitter\_interactions"). It specifies the attribute name, data type (string, json, integer, etc.), and whether it's required. Defined once centrally in MirrorDB per Agent Type. Each definition gets a unique `attr_def_id`.
*   **Agent Attribute:** An *instance* of an Attribute Definition associated with a *specific* agent. It holds the actual value for that agent (e.g., agent 1's "twitter\_username" is "AgentAnon", agent 1's interaction #1 is a JSON blob). Stored centrally in MirrorDB, linked via `agent_id` and `attr_def_id`. Each instance gets a unique `attribute_id`.
*   **Agent Registry:** A central table in MirrorDB where each running agent registers itself, providing its unique Ethereum address and associated Agent Type. Each agent gets a unique `agent_id` upon successful registration.
*   **KV Store:** A *local* key-value storage mechanism used by *each individual agent* to cache frequently needed configuration data like its own `agent_id`, the `twitter_user_id` it's currently using, and the shared `attr_def_id`s for commonly used attributes ("twitter\_username", "twitter\_interactions"). This avoids repeated API calls to MirrorDB for static data.

## Agent Interaction Flows

### 1. Initial Agent Registration (`_register_with_mirror_db`)

This function runs when an agent starts for the first time or if its configuration (`mirrod_db_config`) is missing from its local KV store.

**Steps:**

1.  **Get Twitter User Data:** Calls `_get_twitter_user_data()` (via Twikit connection) to get the `id`, `screen_name`, and `name` for the Twitter account configured for this agent instance.
2.  **Get/Create Agent Type:**
    *   Calls `_call_mirrordb("GET", endpoint="/api/agent-types/name/memeooorr")`.
    *   **If Not Found (First agent of this type):** Calls `_call_mirrordb("POST", endpoint="/api/agent-types/", data={...})` to create the "memeooorr" agent type.
    *   Extracts the `type_id`.
3.  **Create Agent Registry Entry:**
    *   Calls `_call_mirrordb("POST", endpoint="/api/agent-registry/", data={...})` with the agent's `eth_address` and the `type_id`. This registers the unique agent instance.
    *   Extracts the unique `agent_id` for this instance.
4.  **Save Config to Local KV Store:**
    *   Calls `_write_kv()` to save `{"mirrod_db_config": json.dumps({"agent_id": agent_id, "twitter_user_id": twitter_user_id})}` locally.
5.  **Get/Create "twitter\_interactions" Attribute Definition:**
    *   Calls `_call_mirrordb("GET", endpoint="/api/attributes/name/twitter_interactions")`.
    *   **If Not Found (First agent overall):** Calls `_call_mirrordb("POST", endpoint="/api/agent-types/{type_id}/attributes/", data={...}, auth={...})` (requires signing) to create the definition with `data_type="json"`.
    *   Extracts the `attr_def_id` (let's call it `interactions_def_id`).
    *   Calls `_write_kv()` to save `{"twitter_interactions_attr_def_id": str(interactions_def_id)}` locally.
6.  **Get/Create "twitter\_username" Attribute Definition:**
    *   Calls `_call_mirrordb("GET", endpoint="/api/attributes/name/twitter_username")`.
    *   **If Not Found (First agent overall):** Calls `_call_mirrordb("POST", endpoint="/api/agent-types/{type_id}/attributes/", data={...}, auth={...})` (requires signing) to create the definition with `data_type="string"`.
    *   Extracts the `attr_def_id` (let's call it `username_def_id`).
    *   Calls `_write_kv()` to save `{"twitter_username_attr_def_id": str(username_def_id)}` locally.
7.  **Create "twitter\_username" Attribute Instance:**
    *   Calls `_call_mirrordb("POST", endpoint="/api/agents/{agent_id}/attributes/", data={...}, auth={...})` (requires signing) to create an `AgentAttribute` row linking this agent's `agent_id` to the `username_def_id` and storing the actual `twitter_username` (from Step 1) in the `string_value` field.

**Outcome:** The agent is registered in the central MirrorDB, necessary definitions are created (if they didn't exist), and the agent has cached its `agent_id`, `twitter_user_id`, and the relevant `attr_def_id`s in its local KV store.

### 2. Recording Twitter Interactions (`_handle_mirrordb_interaction_post_twikit`)

This runs after the agent successfully performs an action via the Twikit connection (e.g., post, like, retweet, follow).

**Steps:**

1.  **Check Action Type:** Verifies if the `method` (e.g., "post", "like_tweet") is one that needs recording.
2.  **Read Local Config:** Reads `agent_id` from the `mirrod_db_config` in the local KV store.
3.  **Read Interaction Definition ID:** Reads `twitter_interactions_attr_def_id` from the local KV store.
4.  **Construct JSON Payload:** Creates a `json_value` dictionary containing:
    *   `action`: Type of interaction ("post", "like", "retweet", "follow").
    *   `timestamp`: Current UTC timestamp.
    *   `details`: Dictionary with relevant IDs/data (e.g., `{"tweet_id": "...", "text": "..."}` for post, `{"user_id": "..."}` for follow).
5.  **Build Attribute Payload:** Creates the `agent_attr` payload for the API call, including `agent_id`, `attr_def_id` (from Step 3), and the `json_value` (from Step 4). Other value fields (string\_value, etc.) are null.
6.  **Sign Request:** Calls `_sign_mirrordb_request()` to generate the signature and auth block for the target endpoint (`/api/agents/{agent_id}/attributes/`).
7.  **Call MirrorDB:** Calls `_call_mirrordb("POST", endpoint="/api/agents/{agent_id}/attributes/", data={"agent_attr": ..., "auth": ...})`.

**Outcome:** A **new row** is created in the central `agent_attributes` table for *each interaction*. This row links the agent (`agent_id`) to the "twitter\_interactions" definition (`attr_def_id`) and stores the specific details of *that single interaction* in the `json_value` column.

### 3. Checking/Updating Twitter Account (`_handle_mirror_db_interactions_pre_twikit`)

This runs *before* each call to the Twikit connection to ensure the agent's stored information matches the currently logged-in Twitter account.

**Steps:**

1.  **Check Registration:** Calls `_mirror_db_registration_check()` which reads `mirrod_db_config` from the local KV store. If missing, triggers the full registration flow (see Flow 1). Parses the stored `agent_id` and `twitter_user_id`.
2.  **Get Current Cookie User ID:** Calls `_get_twitter_user_id_from_cookie()` (via Twikit) to get the user ID associated with the current session cookies.
3.  **Compare User IDs:** Checks if `twitter_user_id_from_cookie` is different from the `twitter_user_id` stored locally (from Step 1).
4.  **If Different (Account Changed):**
    *   Log a warning.
    *   Update `mirrod_db_config` in the *local* KV store with the *new* `twitter_user_id` using `_update_mirror_db_config_with_new_twitter_user_id()`.
    *   Get the *new* Twitter username by calling `_get_twitter_user_data()` again (using current cookies).
    *   Read the `twitter_username_attr_def_id` from the local KV store.
    *   Attempt to **GET** the existing username `AgentAttribute` instance: `_call_mirrordb("GET", endpoint="/api/agents/{agent_id}/attributes/{username_def_id}/")`.
    *   **If GET successful and returns `attribute_id`:**
        *   Extract the `attribute_id` of the existing instance.
        *   Prepare update payload: `{"string_value": new_twitter_username}`.
        *   Sign the request for `PUT /api/agent-attributes/{attribute_id}`.
        *   Call `_call_mirrordb("PUT", endpoint="/api/agent-attributes/{attribute_id}", data={"agent_attr": ..., "auth": ...})`.
    *   **If GET fails or doesn't return `attribute_id`:**
        *   Log a warning.
        *   Prepare create payload: `{"agent_id": agent_id, "attr_def_id": username_def_id, "string_value": new_twitter_username}`.
        *   Sign the request for `POST /api/agents/{agent_id}/attributes/`.
        *   Call `_call_mirrordb("POST", endpoint="/api/agents/{agent_id}/attributes/", data={"agent_attr": ..., "auth": ...})`.

**Outcome:** If a Twitter account change is detected, the agent updates its local KV store and attempts to update (or create if missing) the central "twitter\_username" `AgentAttribute` record in MirrorDB to reflect the new username.

### 4. Retrieving Recent Handles (`get_recent_memeooorr_handles`)

This function aims to find Twitter handles of other agents who have interacted recently.

**Intended Steps (Requires specific backend endpoints):**

1.  **Read Definition IDs:** Reads `twitter_interactions_attr_def_id` and `twitter_username_attr_def_id` from the local KV store.
2.  **Get All Interaction Instances:** Calls `_call_mirrordb("GET", endpoint="/api/attributes/definition/{interactions_def_id}/instances/")`. ***Assumption: This endpoint exists on the backend.***
3.  **Filter Locally:** Iterates through the returned interaction instances, parses the `timestamp` from the `json_value`, and keeps only those within the last N days (e.g., 7). Extracts the unique `agent_id`s from these recent interactions.
4.  **Get Usernames:** For each unique recent `agent_id`:
    *   Calls `_call_mirrordb("GET", endpoint="/api/agents/{agent_id}/attributes/{username_def_id}/")`. ***Assumption: This endpoint exists on the backend (corrected from `/definition/` path).***
    *   Extracts the `string_value` (the username) from the response.
5.  **Collect Handles:** Appends the retrieved usernames to a list, excluding the agent's own username.
6.  **Return List:** Returns the final list of recent handles.

**Outcome:** Provides a list of Twitter usernames for other Memeooorr agents that have recorded interactions recently. **Note:** This flow depends on backend API endpoints that may not yet be implemented as specified in the assumptions.

## Helper Functions

*   `_call_mirrordb(http_method, endpoint, **kwargs)`: Constructs the payload for the SRR protocol and sends the request to the `MirrorDBConnection`, specifying the HTTP method, endpoint, and any data/auth payload.
*   `_sign_mirrordb_request(endpoint, agent_id)`: Creates the timestamp, message string (`timestamp:{ts},endpoint:{ep}`), signs it using the agent's key, and returns the standard `auth` block required by protected MirrorDB endpoints.
*   `_read_kv(keys)` / `_write_kv(data)`: Handles communication with the `KVStoreConnection` to read/write data to the agent's *local* KV store.

## Summary

The AFMDB 2.0 integration stores agent state and interaction history primarily within the generic `agent_attributes` table. Shared concepts like agent types and data formats are defined once (`AgentType`, `AttributeDefinition`). Each agent instance registers uniquely (`AgentRegistry`) and creates specific `AgentAttribute` rows linked to relevant definitions to store its own username and a chronological record of its individual interactions. Local caching via the KV Store is used to minimize redundant API calls for configuration data.