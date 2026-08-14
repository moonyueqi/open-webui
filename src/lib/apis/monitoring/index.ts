import { WEBUI_API_BASE_URL } from '$lib/constants';

////////////////////
// 地面监测 - 自动站报警
////////////////////

export type GroundAlarmModel = {
	id: string;
	push_time: number | null;
	coverage_start: number | null;
	coverage_end: number | null;
	station_id: string;
	station_name: string | null;
	county: string | null;
	province: string | null;
	observed_at: number;
	pre: number | null;
	rain_5m: number | null;
	rain_10m: number | null;
	rain_15m: number | null;
	rain_20m: number | null;
	rain_25m: number | null;
	rain_30m: number | null;
	level: string | null;
	source_file: string;
	created_at: number;
};

export type GroundAlarmListResponse = {
	items: GroundAlarmModel[];
	total: number;
};

export type GroundAlarmSummaryResponse = {
	active_count: number;
	by_level: Record<string, number>;
	county_count: number;
	latest_alarm_at: number | null;
	updated_at: number | null;
};

export type GroundAlarmQuery = {
	level?: string[];
	county?: string;
	station_id?: string;
	start?: number;
	end?: number;
	latest_only?: boolean;
	skip?: number;
	limit?: number;
};

const buildQuery = (params: Record<string, unknown>): string => {
	const search = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value === undefined || value === null || value === '') continue;
		if (Array.isArray(value)) {
			for (const v of value) search.append(key, String(v));
		} else {
			search.append(key, String(value));
		}
	}
	const qs = search.toString();
	return qs ? `?${qs}` : '';
};

const authedFetch = async <T>(token: string, path: string): Promise<T> => {
	let error: any = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/monitoring${path}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err?.detail ?? err;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res as T;
};

export const getGroundAlarms = (
	token: string,
	query: GroundAlarmQuery = {}
): Promise<GroundAlarmListResponse> =>
	authedFetch(token, `/ground/alarms${buildQuery(query)}`);

export const getGroundSummary = (token: string): Promise<GroundAlarmSummaryResponse> =>
	authedFetch(token, `/ground/summary`);

export const getGroundAlarmById = (token: string, id: string): Promise<GroundAlarmModel> =>
	authedFetch(token, `/ground/alarms/${id}`);

////////////////////
// 高空预警 - 闪电跃增预警
////////////////////

export type LightningPushModel = {
	id: string;
	push_time: number | null;
	coverage_start: number | null;
	coverage_end: number | null;
	csv_path: string;
	json_path: string | null;
	png_path: string | null;
	created_at: number;
};

export type LightningPushSummary = LightningPushModel & {
	event_count: number;
	events: LightningJumpEventModel[];
};

export type LightningPushListResponse = {
	items: LightningPushSummary[];
	total: number;
};

export type LightningJumpEventModel = {
	id: string;
	push_id: string;
	cell_seq: string | null;
	region: string;
	jump_times: string | null;
	created_at: number;
};

export type LightningPushDetailResponse = {
	push: LightningPushModel;
	events: LightningJumpEventModel[];
};

export const getLightningPushes = (
	token: string,
	params: { skip?: number; limit?: number } = {}
): Promise<LightningPushListResponse> =>
	authedFetch(token, `/lightning/pushes${buildQuery(params)}`);

export const getLightningPushDetail = (
	token: string,
	id: string
): Promise<LightningPushDetailResponse> => authedFetch(token, `/lightning/pushes/${id}`);

export const getLightningPushImageUrl = (id: string): string =>
	`${WEBUI_API_BASE_URL}/monitoring/lightning/pushes/${id}/image`;

////////////////////
// 侧边栏播报 Feed
////////////////////

export type AlertFeedItem = {
	id: string;
	type: 'ground' | 'lightning';
	level: string | null;
	text: string;
	target: string;
	record_id: string;
	occurred_at: number;
};

export type AlertFeedResponse = {
	items: AlertFeedItem[];
};

export const getAlertsFeed = (token: string, limit = 5): Promise<AlertFeedResponse> =>
	authedFetch(token, `/alerts/feed${buildQuery({ limit })}`);
