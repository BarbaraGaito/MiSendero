import { AuthResponse, Profile, Trail, TrailReport, TrailWeather } from "../types";
import Constants from "expo-constants";
import { Platform } from "react-native";

const API_PORT = "3001";

const getApiUrl = () => {
  const expoHost = Constants.expoConfig?.hostUri?.split(":")[0];
  const host = expoHost || (Platform.OS === "android" ? "10.0.2.2" : "localhost");

  return `http://${host}:${API_PORT}/api`;
};

const API_URL = getApiUrl();

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
  token?: string;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};

  if (options.body) {
    headers["Content-Type"] = "application/json";
  }

  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  let response: Response;

  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch (error) {
    throw new Error(`No se pudo conectar con el backend en ${API_URL}.`);
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(errorBody?.message || "No se pudo completar la solicitud");
  }

  return response.json();
}

export const loginUser = async (
  email: string,
  password: string
): Promise<AuthResponse> => {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
  });
};

export const registerUser = async (
  name: string,
  email: string,
  password: string,
  acceptedTermsVersion: string
): Promise<AuthResponse> => {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: {
      name,
      email,
      password,
      accepted_terms_version: acceptedTermsVersion,
    },
  });
};

export const getTrails = async (): Promise<Trail[]> => {
  return request<Trail[]>("/trails");
};

export const getTrailById = async (id: number): Promise<Trail> => {
  return request<Trail>(`/trails/${id}`);
};

export const getTrailWeather = async (id: number): Promise<TrailWeather> => {
  return request<TrailWeather>(`/trails/${id}/weather`);
};

export const getTrailReports = async (id: number): Promise<TrailReport[]> => {
  return request<TrailReport[]>(`/trails/${id}/reports`);
};

export const createTrailReport = async (
  trailId: number,
  report: {
    issue_summary: string;
    severity: string;
    trail_state: string;
    cause?: string | null;
    blocks_path?: boolean;
    details?: string;
  }
): Promise<TrailReport> => {
  return request<TrailReport>(`/trails/${trailId}/reports`, {
    method: "POST",
    body: report,
  });
};

export const getProfile = async (token: string): Promise<Profile> => {
  return request<Profile>("/auth/me", { token });
};
