<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	const i18n = getContext('i18n');

	import { goto } from '$app/navigation';

	import {
		uploadPreprocessJob,
		getPreprocessJob,
		downloadPreprocessResult,
		deletePreprocessJob
	} from '$lib/apis/documentPreprocessing';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import FilesOverlay from '$lib/components/chat/MessageInput/FilesOverlay.svelte';

	// MinerU 支持的类型
	const ACCEPT = '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx';
	const ALLOWED = new Set(['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx']);

	const STORAGE_KEY = 'documentPreprocessJobId';

	let loaded = false;
	let dragged = false;

	let selectedFiles: File[] = [];
	let inputFiles: FileList | null = null;
	let fileInputEl: HTMLInputElement;

	// job 状态
	let job: any = null;
	let uploading = false;
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	$: isActive = job && (job.status === 'queued' || job.status === 'running');
	$: isCompleted = job && job.status === 'completed';
	$: isFailedOrInterrupted =
		job && (job.status === 'failed' || job.status === 'interrupted');
	$: percentage =
		job && job.total > 0 ? Math.floor(((job.done ?? 0) / job.total) * 100) : 0;

	const filterFiles = (files: File[]) => {
		const accepted: File[] = [];
		for (const file of files) {
			const ext = (file.name.split('.').pop() ?? '').toLowerCase();
			if (ALLOWED.has(ext)) {
				accepted.push(file);
			} else {
				toast.error($i18n.t('Unsupported file type: {{name}}', { name: file.name }));
			}
		}
		return accepted;
	};

	const addFiles = (files: File[]) => {
		const accepted = filterFiles(files);
		if (accepted.length === 0) return;
		// 去重（按 name+size）
		const existing = new Set(selectedFiles.map((f) => `${f.name}:${f.size}`));
		for (const f of accepted) {
			const key = `${f.name}:${f.size}`;
			if (!existing.has(key)) {
				selectedFiles = [...selectedFiles, f];
				existing.add(key);
			}
		}
	};

	const removeFile = (index: number) => {
		selectedFiles = selectedFiles.filter((_, i) => i !== index);
	};

	const onDragOver = (e: DragEvent) => {
		e.preventDefault();
		if (e.dataTransfer?.types?.includes('Files')) {
			dragged = true;
		}
	};

	const onDragLeave = (e: DragEvent) => {
		e.preventDefault();
		dragged = false;
	};

	const onDrop = (e: DragEvent) => {
		e.preventDefault();
		dragged = false;
		if (e.dataTransfer?.files) {
			addFiles(Array.from(e.dataTransfer.files));
		}
	};

	const startPolling = (jobId: string) => {
		stopPolling();
		pollTimer = setInterval(async () => {
			const res = await getPreprocessJob(localStorage.token, jobId).catch(() => null);
			if (res) {
				job = res;
				if (!(job.status === 'queued' || job.status === 'running')) {
					stopPolling();
				}
			}
		}, 2000);
	};

	const stopPolling = () => {
		if (pollTimer) {
			clearInterval(pollTimer);
			pollTimer = null;
		}
	};

	const submitHandler = async () => {
		if (selectedFiles.length === 0) {
			toast.error($i18n.t('Please select at least one file.'));
			return;
		}
		uploading = true;
		try {
			const res = await uploadPreprocessJob(localStorage.token, selectedFiles);
			if (res?.id) {
				localStorage.setItem(STORAGE_KEY, res.id);
				job = res;
				selectedFiles = [];
				startPolling(res.id);
			}
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			uploading = false;
		}
	};

	const downloadHandler = async () => {
		if (!job?.id) return;
		try {
			const blob = await downloadPreprocessResult(localStorage.token, job.id);
			if (blob) {
				const url = URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = `preprocess-${job.id}.zip`;
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);
				URL.revokeObjectURL(url);
			}
		} catch (e) {
			toast.error(`${e}`);
		}
	};

	const resetHandler = async () => {
		if (job?.id) {
			await deletePreprocessJob(localStorage.token, job.id).catch(() => {});
		}
		stopPolling();
		localStorage.removeItem(STORAGE_KEY);
		job = null;
		selectedFiles = [];
	};

	onMount(async () => {
		// 恢复正在进行/已完成的任务
		const savedId = localStorage.getItem(STORAGE_KEY);
		if (savedId) {
			const res = await getPreprocessJob(localStorage.token, savedId).catch(() => null);
			if (res) {
				job = res;
				if (job.status === 'queued' || job.status === 'running') {
					startPolling(savedId);
				}
			} else {
				localStorage.removeItem(STORAGE_KEY);
			}
		}
		loaded = true;
	});

	onDestroy(() => {
		stopPolling();
	});
</script>

<svelte:body on:dragover={onDragOver} on:dragleave={onDragLeave} on:drop={onDrop} />

<FilesOverlay show={dragged} />

<input
	bind:this={fileInputEl}
	bind:files={inputFiles}
	type="file"
	multiple
	hidden
	accept={ACCEPT}
	on:change={() => {
		if (inputFiles && inputFiles.length > 0) {
			addFiles(Array.from(inputFiles));
			inputFiles = null;
			fileInputEl.value = '';
		}
	}}
/>

{#if loaded}
	<div class="flex flex-col h-full min-h-0 overflow-hidden">
		<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
			<div class="flex justify-between items-center">
				<div class="flex items-center gap-3 shrink-0">
					<button
						class="flex items-center justify-center w-9 h-9 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 transition"
						on:click={() => goto('/workspace/knowledge')}
						aria-label={$i18n.t('Back')}
					>
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
						</svg>
					</button>
					<div>
						<div class="text-xl font-semibold">{$i18n.t('Document Preprocessing')}</div>
						<div class="text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('Upload documents to convert into knowledge-ready Markdown')}
						</div>
					</div>
				</div>
			</div>
		</div>

		<div
			class="py-4 px-4 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm min-h-0 flex flex-col overflow-hidden"
			style="flex: 1 1 0;"
		>
			{#if job}
				<!-- 任务进行/完成视图 -->
				<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden">
					<div class="flex flex-col gap-4 max-w-2xl mx-auto w-full mt-2">
						{#if isActive}
							<div class="flex items-center gap-2 text-sm">
								<Spinner className="size-4" />
								{#if job.status === 'queued'}
									<span>{$i18n.t('Queued...')}</span>
								{:else}
									<span>
										{$i18n.t('Processing {{done}}/{{total}}', {
											done: job.done ?? 0,
											total: job.total ?? 0
										})}
									</span>
								{/if}
							</div>

							<div class="w-full rounded-full bg-gray-100 dark:bg-gray-800">
								<div
									class="bg-emerald-500 dark:bg-emerald-600 text-xs font-medium text-white text-center p-0.5 leading-none rounded-full transition-all"
									style="width: {Math.max(6, percentage)}%"
								>
									{percentage}%
								</div>
							</div>

							{#if job.current_file}
								<div class="text-xs text-gray-500 dark:text-gray-400 truncate">
									{$i18n.t('Current file')}: {job.current_file}
								</div>
							{/if}
						{:else if isCompleted}
							<div class="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400 font-medium">
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-5">
									<path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z" clip-rule="evenodd" />
								</svg>
								<span>{$i18n.t('Processing complete')}</span>
							</div>
							<div class="text-xs text-gray-500 dark:text-gray-400">
								{$i18n.t('Success')}: {job.success ?? 0} · {$i18n.t('Failed')}: {job.failed ?? 0} · {$i18n.t('Skipped')}: {job.skipped ?? 0}
							</div>
						{:else if isFailedOrInterrupted}
							<div class="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 font-medium">
								<span>
									{job.status === 'interrupted'
										? $i18n.t('Job interrupted, please retry')
										: $i18n.t('Processing failed')}
								</span>
							</div>
						{/if}

						{#if job.errors && job.errors.length > 0}
							<div class="rounded-xl border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/10 px-3 py-2 text-xs text-red-700 dark:text-red-300">
								<div class="font-medium mb-1">{$i18n.t('Errors')}:</div>
								<ul class="list-disc list-inside space-y-0.5">
									{#each job.errors as err}
										<li class="break-all">{err}</li>
									{/each}
								</ul>
							</div>
						{/if}

						<div class="flex gap-2 mt-2">
							{#if isCompleted}
								<button
									class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium flex items-center gap-1.5 transition"
									on:click={downloadHandler}
								>
									<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-4">
										<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
									</svg>
									{$i18n.t('Download Result')}
								</button>
							{/if}
							<button
								class="px-4 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-sm font-medium transition disabled:opacity-50"
								on:click={resetHandler}
								disabled={isActive}
							>
								{$i18n.t('New Task')}
							</button>
						</div>
					</div>
				</div>
			{:else}
				<!-- 上传视图 -->
				<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden flex flex-col">
					<button
						class="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-2xl py-12 hover:border-emerald-400 dark:hover:border-emerald-600 transition"
						on:click={() => fileInputEl.click()}
					>
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-10 text-gray-400">
							<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
						</svg>
						<div class="text-sm font-medium">{$i18n.t('Click or drag files here to upload')}</div>
						<div class="text-xs text-gray-400">{$i18n.t('Supported: PDF, Word, PowerPoint, Excel')}</div>
					</button>

					{#if selectedFiles.length > 0}
						<div class="mt-4 flex flex-col gap-1.5">
							{#each selectedFiles as file, index}
								<div class="flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-gray-50 dark:bg-gray-850 text-sm">
									<div class="truncate flex-1">{file.name}</div>
									<div class="text-xs text-gray-400 shrink-0">
										{(file.size / 1024 / 1024).toFixed(2)} MB
									</div>
									<button
										class="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition shrink-0"
										on:click={() => removeFile(index)}
										aria-label={$i18n.t('Remove')}
									>
										<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-3.5">
											<path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
										</svg>
									</button>
								</div>
							{/each}
						</div>
					{/if}
				</div>

				<div class="flex justify-end gap-2 pt-3 shrink-0">
					<button
						class="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium flex items-center gap-1.5 transition disabled:opacity-50"
						on:click={submitHandler}
						disabled={uploading || selectedFiles.length === 0}
					>
						{#if uploading}
							<Spinner className="size-4" />
							{$i18n.t('Uploading...')}
						{:else}
							{$i18n.t('Start Processing')}
						{/if}
					</button>
				</div>
			{/if}
		</div>

		<div class="flex items-center gap-1.5 text-gray-400 dark:text-gray-500 text-xs mt-2 mb-1 ml-1 shrink-0">
			<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-3.5 shrink-0">
				<path stroke-linecap="round" stroke-linejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
			</svg>
			{$i18n.t('Processing runs on the server. You can leave this page and come back later.')}
		</div>
	</div>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner className="size-5" />
	</div>
{/if}
