/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import type { AxiosInstance, AxiosRequestConfig } from "axios";
import { create } from "axios";
import { takeEarlyGet } from "@/lib/early-gets";

/** A 401 sends the person to sign in, then comes back here. */
const redirectOnUnauthorized = (error: any) => {
  if (error?.response && error.response.status === 401) {
    const currentPath = window.location.pathname;
    window.location.replace(`/${currentPath ? `?next_path=${currentPath}` : ``}`);
  }
  return Promise.reject(error);
};

export abstract class APIService {
  protected baseURL: string;
  private axiosInstance: AxiosInstance;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.axiosInstance = create({
      baseURL,
      withCredentials: true,
    });

    this.setupInterceptors();
  }

  private setupInterceptors() {
    this.axiosInstance.interceptors.response.use(
      (response) => response,
      redirectOnUnauthorized
    );
  }

  get(url: string, params = {}, config: AxiosRequestConfig = {}) {
    // a plain GET the entry script already started (see lib/early-gets.ts)
    if (Object.keys(params).length === 0 && Object.keys(config).length === 0) {
      const early = takeEarlyGet(this.baseURL + url);
      if (early) return early.catch(redirectOnUnauthorized);
    }
    return this.axiosInstance.get(url, {
      ...params,
      ...config,
    });
  }

  post(url: string, data = {}, config: AxiosRequestConfig = {}) {
    return this.axiosInstance.post(url, data, config);
  }

  put(url: string, data = {}, config: AxiosRequestConfig = {}) {
    return this.axiosInstance.put(url, data, config);
  }

  patch(url: string, data = {}, config: AxiosRequestConfig = {}) {
    return this.axiosInstance.patch(url, data, config);
  }

  delete(url: string, data?: any, config: AxiosRequestConfig = {}) {
    return this.axiosInstance.delete(url, { data, ...config });
  }

  request(config = {}) {
    return this.axiosInstance(config);
  }
}
