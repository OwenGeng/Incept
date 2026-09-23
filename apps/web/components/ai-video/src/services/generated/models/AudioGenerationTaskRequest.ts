/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A narration script or a music brief submitted as a durable task.
 */
export type AudioGenerationTaskRequest = {
    /**
     * Whether the selected model produces speech or music.
     */
    generation_kind: 'speech' | 'music';
    /**
     * Narration script or music prompt.
     */
    prompt: string;
    /**
     * Optional models.id; otherwise the matching default is used.
     */
    model_id?: (string | null);
    /**
     * Optional speech voice.
     */
    voice?: (string | null);
    response_format?: 'mp3' | 'wav' | 'opus' | 'aac' | 'flac' | 'pcm';
    speed?: (number | null);
    provider_params?: Record<string, any>;
};
