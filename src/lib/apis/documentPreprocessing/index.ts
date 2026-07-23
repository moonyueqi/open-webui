import { WEBUI_API_BASE_URL } from '$lib/constants';

export const verifyPreprocessService = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/document-preprocessing/health`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || `${err}`;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const uploadPreprocessJob = async (token: string, files: File[]) => {
	let error = null;

	const data = new FormData();
	for (const file of files) {
		data.append('files', file);
	}

	const res = await fetch(`${WEBUI_API_BASE_URL}/document-preprocessing/jobs`, {
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
			error = err.detail || err.message || `${err}`;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getPreprocessJob = async (token: string, jobId: string) => {
	let error: any = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/document-preprocessing/jobs/${jobId}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				// 附带 HTTP status，便于调用方区分 404（已过期清理）与网络错误
				throw { status: res.status, detail: payload?.detail };
			}
			return res.json();
		})
		.catch((err) => {
			error = { status: err?.status, detail: err?.detail || err?.message || `${err}` };
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deletePreprocessJob = async (token: string, jobId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/document-preprocessing/jobs/${jobId}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || `${err}`;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const downloadPreprocessResult = async (token: string, jobId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/document-preprocessing/jobs/${jobId}/download`, {
		method: 'GET',
		headers: {
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw { status: res.status, detail: payload?.detail };
			}
			return res.blob();
		})
		.catch((err) => {
			error = { status: err?.status, detail: err?.detail || err?.message || `${err}` };
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
