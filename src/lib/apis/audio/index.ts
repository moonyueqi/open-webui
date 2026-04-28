import { AUDIO_API_BASE_URL } from '$lib/constants';

export const getAudioConfig = async (token: string) => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/config`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

type OpenAIConfigForm = {
	url: string;
	key: string;
	model: string;
	speaker: string;
};

export const updateAudioConfig = async (token: string, payload: OpenAIConfigForm) => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/config/update`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			...payload
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const transcribeAudio = async (token: string, file: File, language?: string) => {
	const data = new FormData();
	data.append('file', file);
	if (language) {
		data.append('language', language);
	}

	let error = null;
	const res = await fetch(`${AUDIO_API_BASE_URL}/transcriptions`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		},
		body: data
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const synthesizeOpenAISpeech = async (
	token: string = '',
	speaker: string = 'alloy',
	text: string = '',
	model?: string
) => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/speech`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			input: text,
			voice: speaker,
			...(model && { model })
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res;
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);

			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

interface AvailableModelsResponse {
	models: { name: string; id: string }[] | { id: string }[];
}

export const getModels = async (token: string = ''): Promise<AvailableModelsResponse> => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/models`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);

			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export type ModelVerifyResult = {
	ok: boolean;
	stage?: 'connection' | 'auth' | 'endpoint' | 'model' | 'timeout' | 'input';
	status?: number;
	model?: string;
	message?: string;
};

// 后端的 verify 接口在所有"业务级失败"(鉴权失败 / 模型不存在 / 上游 4xx 等)
// 都会以 HTTP 200 + { ok:false, stage:... } 的形式返回,真正只有网络/进程级
// 错误才会触发 fetch 的 reject 或非 2xx。这里因此优先解析 JSON 拿后端给出的
// stage,只有在 JSON 解析失败时才回退到 connection,以避免把"401 鉴权失败"
// 之类的情况误报成"无法连接服务器"。
const parseVerifyResponse = async (r: Response): Promise<ModelVerifyResult> => {
	try {
		const data = (await r.json()) as ModelVerifyResult;
		if (data && typeof data === 'object' && 'ok' in data) {
			return data;
		}
	} catch (_) {
		// fall through
	}
	if (!r.ok) {
		if (r.status === 401 || r.status === 403) {
			return { ok: false, stage: 'auth', status: r.status };
		}
		if (r.status === 404) {
			return { ok: false, stage: 'endpoint', status: r.status };
		}
		return { ok: false, stage: 'connection', status: r.status };
	}
	return { ok: false, stage: 'connection' };
};

export const verifyTTSModel = async (
	token: string,
	payload: { url: string; key: string; model: string }
): Promise<ModelVerifyResult> => {
	const res = await fetch(`${AUDIO_API_BASE_URL}/tts/verify`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify(payload)
	})
		.then(parseVerifyResponse)
		.catch(() => ({ ok: false, stage: 'connection' as const }));

	return res;
};

export const verifySTTModel = async (
	token: string,
	payload: { url: string; key: string; model: string }
): Promise<ModelVerifyResult> => {
	const res = await fetch(`${AUDIO_API_BASE_URL}/stt/verify`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify(payload)
	})
		.then(parseVerifyResponse)
		.catch(() => ({ ok: false, stage: 'connection' as const }));

	return res;
};

export const getVoices = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${AUDIO_API_BASE_URL}/voices`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);

			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
