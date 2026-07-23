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
	const EXT_LABEL = 'PDF · DOC · DOCX · PPT · PPTX · XLS · XLSX';

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

	// 右侧结果列表：优先用后端逐文件明细，否则回退到 errors
	$: fileResults = (job?.file_results ?? []) as { name: string; status: string; error?: string }[];
	$: successFiles = fileResults.filter((f) => f.status === 'success');
	$: failedFiles = fileResults.filter((f) => f.status === 'failed');
	$: skippedFiles = fileResults.filter((f) => f.status === 'skipped');
	// 左栏只负责“待上传”：点击开始处理后清空 selectedFiles，左栏自然回到空态。
	// 已提交/处理中的文件由右栏（进度 + 当前文件 + 逐文件结果）负责展示。
	$: leftFiles = selectedFiles.map((f) => ({ name: f.name, size: f.size }));

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
		if (job) return; // 任务进行/完成时不接受新增
		const accepted = filterFiles(files);
		if (accepted.length === 0) return;
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

	const totalSize = (files: { size: number }[]) =>
		files.reduce((acc, f) => acc + f.size, 0);

	const formatSize = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(2)} MB`;

	const onDragOver = (e: DragEvent) => {
		e.preventDefault();
		if (!job && e.dataTransfer?.types?.includes('Files')) {
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
		if (!job && e.dataTransfer?.files) {
			addFiles(Array.from(e.dataTransfer.files));
		}
	};

	// job 已被服务端 TTL 清理（404）时，重置界面并提示，避免用户对着失效任务操作
	const handleExpired = () => {
		stopPolling();
		localStorage.removeItem(STORAGE_KEY);
		job = null;
		selectedFiles = [];
		toast.error($i18n.t('This task has expired and been cleaned up. Please upload again.'));
	};

	const startPolling = (jobId: string) => {
		stopPolling();
		pollTimer = setInterval(async () => {
			let expired = false;
			const res = await getPreprocessJob(localStorage.token, jobId).catch((e) => {
				if (e?.status === 404) expired = true;
				return null;
			});
			if (expired) {
				handleExpired();
				return;
			}
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
		} catch (e: any) {
			toast.error(e?.detail ?? `${e}`);
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
		} catch (e: any) {
			if (e?.status === 404) {
				handleExpired();
			} else {
				toast.error(e?.detail ?? `${e}`);
			}
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
		<!-- 头部 -->
		<div class="flex items-center justify-between px-1 mt-1.5 mb-4 shrink-0">
			<div class="flex items-center gap-3">
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

			{#if job}
				<button
					class="px-3.5 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-sm font-medium transition disabled:opacity-50 shrink-0"
					on:click={resetHandler}
					disabled={isActive}
				>
					{$i18n.t('New Task')}
				</button>
			{/if}
		</div>

		<!-- 主体：左右两栏 -->
		<div class="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-2 gap-3 overflow-hidden">
			<!-- 左栏：上传 & 文件列表 -->
			<div class="flex flex-col min-h-0 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm overflow-hidden">
				<div class="flex items-center justify-between px-4 pt-3.5 pb-2 shrink-0">
					<div class="text-sm font-semibold">
						{$i18n.t('Files to upload')}
						{#if leftFiles.length > 0}
							<span class="text-gray-400 dark:text-gray-500 font-normal">({leftFiles.length})</span>
						{/if}
					</div>
					{#if !job && selectedFiles.length > 0}
						<button
							class="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition"
							on:click={() => (selectedFiles = [])}
						>
							{$i18n.t('Clear all')}
						</button>
					{/if}
				</div>

				{#if !job}
					<!-- 紧凑上传条 -->
					<div class="px-4 shrink-0">
						<button
							class="w-full flex items-center gap-3 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3 hover:-translate-y-px hover:shadow-sm hover:border-gray-300 dark:hover:border-gray-600 transition-all duration-200 text-left"
							on:click={() => fileInputEl.click()}
						>
							<div class="flex items-center justify-center w-9 h-9 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 text-emerald-500 shrink-0">
								<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5">
									<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
								</svg>
							</div>
							<div class="min-w-0">
								<div class="text-sm font-medium">{$i18n.t('Click or drag files here to upload')}</div>
								<div class="text-xs text-gray-400 truncate">{$i18n.t('Supported')}: {EXT_LABEL}</div>
							</div>
						</button>
					</div>
				{/if}

				<!-- 文件列表 -->
				<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden px-4 py-3">
					{#if leftFiles.length > 0}
						<div class="flex flex-col gap-1.5">
							{#each leftFiles as file, index}
								<div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-gray-50 dark:bg-gray-850 text-sm">
									<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-4 text-gray-400 shrink-0">
										<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
									</svg>
									<div class="truncate flex-1">{file.name}</div>
									{#if file.size > 0}
										<div class="text-xs text-gray-400 shrink-0">{formatSize(file.size)}</div>
									{/if}
									{#if !job}
										<button
											class="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition shrink-0"
											on:click={() => removeFile(index)}
											aria-label={$i18n.t('Remove')}
										>
											<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-3.5">
												<path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
											</svg>
										</button>
									{/if}
								</div>
							{/each}
						</div>
					{:else}
						<div class="h-full flex flex-col items-center justify-center text-center text-gray-300 dark:text-gray-600 gap-2 py-8">
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-8">
								<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
							</svg>
							<div class="text-xs">
								{#if job}
									{$i18n.t('Files submitted. Start a new task to upload more.')}
								{:else}
									{$i18n.t('No files selected yet')}
								{/if}
							</div>
						</div>
					{/if}
				</div>

				{#if !job}
					<div class="px-4 py-3 border-t border-gray-100 dark:border-gray-800/60 shrink-0 flex items-center justify-between">
						<div class="text-xs text-gray-400">
							{#if selectedFiles.length > 0}
								{$i18n.t('Total')}: {formatSize(totalSize(selectedFiles))}
							{/if}
						</div>
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

			<!-- 右栏：处理状态 & 结果 -->
			<div class="flex flex-col min-h-0 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm overflow-hidden">
				<div class="flex items-center justify-between px-4 pt-3.5 pb-2 shrink-0">
					<div class="text-sm font-semibold">{$i18n.t('Processing result')}</div>
					{#if isCompleted}
						<button
							class="px-3.5 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium flex items-center gap-1.5 transition"
							on:click={downloadHandler}
						>
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-3.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
							</svg>
							{$i18n.t('Download')}
						</button>
					{/if}
				</div>

				<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden px-4 py-3">
					{#if !job}
						<div class="h-full flex flex-col items-center justify-center text-center text-gray-300 dark:text-gray-600 gap-2 py-8">
							<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-8">
								<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12.76c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
							</svg>
							<div class="text-xs">{$i18n.t('Results will appear here after processing')}</div>
						</div>
					{:else}
						<div class="flex flex-col gap-4">
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

								<!-- 统计徽章 -->
								<div class="grid grid-cols-3 gap-2">
									<div class="rounded-xl bg-emerald-50 dark:bg-emerald-900/15 px-3 py-2 text-center">
										<div class="text-lg font-semibold text-emerald-600 dark:text-emerald-400">{job.success ?? 0}</div>
										<div class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('Success')}</div>
									</div>
									<div class="rounded-xl bg-red-50 dark:bg-red-900/15 px-3 py-2 text-center">
										<div class="text-lg font-semibold text-red-600 dark:text-red-400">{job.failed ?? 0}</div>
										<div class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('Failed')}</div>
									</div>
									<div class="rounded-xl bg-gray-50 dark:bg-gray-850 px-3 py-2 text-center">
										<div class="text-lg font-semibold text-gray-500 dark:text-gray-400">{job.skipped ?? 0}</div>
										<div class="text-xs text-gray-500 dark:text-gray-400">{$i18n.t('Skipped')}</div>
									</div>
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

							<!-- 逐文件结果分组 -->
							{#if isCompleted && fileResults.length > 0}
								{#if failedFiles.length > 0}
									<div>
										<div class="text-xs font-medium text-red-600 dark:text-red-400 mb-1.5">
											{$i18n.t('Failed')} ({failedFiles.length})
										</div>
										<div class="flex flex-col gap-1">
											{#each failedFiles as f}
												<div class="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/10 text-xs">
													<div class="truncate font-medium text-red-700 dark:text-red-300">{f.name}</div>
													{#if f.error}
														<div class="text-red-500/80 dark:text-red-400/70 break-all mt-0.5">{f.error}</div>
													{/if}
												</div>
											{/each}
										</div>
									</div>
								{/if}

								{#if successFiles.length > 0}
									<div>
										<div class="text-xs font-medium text-emerald-600 dark:text-emerald-400 mb-1.5">
											{$i18n.t('Success')} ({successFiles.length})
										</div>
										<div class="flex flex-col gap-1">
											{#each successFiles as f}
												<div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-850 text-xs">
													<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-3.5 text-emerald-500 shrink-0">
														<path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z" clip-rule="evenodd" />
													</svg>
													<div class="truncate">{f.name}</div>
												</div>
											{/each}
										</div>
									</div>
								{/if}

								{#if skippedFiles.length > 0}
									<div>
										<div class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
											{$i18n.t('Skipped')} ({skippedFiles.length})
										</div>
										<div class="flex flex-col gap-1">
											{#each skippedFiles as f}
												<div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-850 text-xs text-gray-500 dark:text-gray-400">
													<div class="truncate">{f.name}</div>
												</div>
											{/each}
										</div>
									</div>
								{/if}
							{:else if job.errors && job.errors.length > 0}
								<!-- 回退：无逐文件明细时显示 errors -->
								<div class="rounded-xl border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/10 px-3 py-2 text-xs text-red-700 dark:text-red-300">
									<div class="font-medium mb-1">{$i18n.t('Errors')}:</div>
									<ul class="list-disc list-inside space-y-0.5">
										{#each job.errors as err}
											<li class="break-all">{err}</li>
										{/each}
									</ul>
								</div>
							{/if}
						</div>
					{/if}
				</div>
			</div>
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
