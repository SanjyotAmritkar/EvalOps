/**
 * Hand-written mirrors of the FastAPI response/request schemas the dashboard
 * uses. Kept minimal — only what CP 3.1 touches. (Generation from the live
 * OpenAPI schema is deferred; see the Phase 3 plan.)
 */

export interface Project {
  id: string;
  name: string;
  created_at: string;
}

export interface ProjectCreate {
  name: string;
}
