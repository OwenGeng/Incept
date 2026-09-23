/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModelCategoryKey } from './ModelCategoryKey';
/**
 * 创建模型请求体。
 */
export type ModelCreate = {
    /**
     * 模型名称
     */
    name: string;
    /**
     * Model category.
     */
    category: ModelCategoryKey;
    /**
     * 所属供应商 ID
     */
    provider_id: string;
    /**
     * 模型参数（JSON）
     */
    params?: Record<string, any>;
    /**
     * 说明
     */
    description?: string;
    /**
     * 创建人
     */
    created_by?: string;
    /**
     * 模型 ID
     */
    id: string;
};
