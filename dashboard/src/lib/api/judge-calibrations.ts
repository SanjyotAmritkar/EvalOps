import { apiFetch } from "./client";
import type { JudgeCalibration, JudgeCalibrationCreate } from "./types";

export function listJudgeCalibrations(): Promise<JudgeCalibration[]> {
  return apiFetch<JudgeCalibration[]>("/judge-calibrations");
}

export function getJudgeCalibration(id: string): Promise<JudgeCalibration> {
  return apiFetch<JudgeCalibration>(`/judge-calibrations/${id}`);
}

export function createJudgeCalibration(
  body: JudgeCalibrationCreate,
): Promise<JudgeCalibration> {
  return apiFetch<JudgeCalibration>("/judge-calibrations", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
