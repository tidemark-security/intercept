/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__api__routes__auth__UserSummary } from './app__api__routes__auth__UserSummary';
import type { SessionSummary } from './SessionSummary';
export type LoginResponse = {
    user: app__api__routes__auth__UserSummary;
    session: SessionSummary;
    mustChangePassword?: boolean;
};

