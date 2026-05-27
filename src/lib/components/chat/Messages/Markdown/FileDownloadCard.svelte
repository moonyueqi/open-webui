<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { formatFileSize } from '$lib/utils';
	import { getFileById } from '$lib/apis/files';
	import { user as _user } from '$lib/stores';
	import { get } from 'svelte/store';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Download from '$lib/components/icons/Download.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import FileItemModal from '$lib/components/common/FileItemModal.svelte';

	const i18n = getContext('i18n');

	/**
	 * Original markdown link href (e.g. /api/v1/files/<id>/content)
	 */
	export let href: string;

	/**
	 * Fallback display name (text shown inside the markdown link)
	 */
	export let fallbackName: string = '';

	/**
	 * Whether the surrounding markdown stream has finished. While `false`,
	 * partial autolinks of the file URL may pass through as the fallback
	 * name; we suppress that until streaming finishes (or until we have a
	 * real filename from the API).
	 */
	export let done: boolean = true;

	let fileId: string = '';
	let fileItem: any = null;
	let displayName: string = '';
	let loading = true;
	let showModal = false;

	/**
	 * Heuristic: a fallback that looks like an http(s) URL or a partial
	 * `/api/v1/files/...` path is not a real filename and should not be
	 * shown to the user during streaming.
	 */
	const looksLikeUrl = (s: string): boolean => {
		const t = (s || '').trim();
		if (!t) return false;
		if (/^https?:\/\//i.test(t)) return true;
		if (t.startsWith('/api/v1/files/')) return true;
		return false;
	};

	const extractFileId = (url: string): string => {
		try {
			const m = url.match(/\/api\/v1\/files\/([0-9a-fA-F-]{8,})/);
			return m ? m[1] : '';
		} catch {
			return '';
		}
	};

	const cleanFallbackName = (raw: string): string => {
		// Tool scripts often output something like "📄 下载 filename.docx"
		// Strip leading icon characters and a generic "下载/Download" verb to keep the filename clean.
		let s = (raw || '').trim();
		// If the fallback text is just (a prefix of) the file URL itself,
		// it's not a real display name; bail out early.
		if (looksLikeUrl(s)) return '';
		try {
			// Remove leading symbols / pictographs (most emoji ranges) using Unicode property escapes
			s = s.replace(/^[\s\p{Extended_Pictographic}\p{S}\p{P}]+/u, '');
		} catch {
			// Fallback for environments without Unicode property escape support
			s = s.replace(/^[^\p{L}\p{N}]+/u, '');
		}
		s = s.replace(/^(下载|Download)\s*[:：]?\s*/i, '');
		s = s.trim();
		// Re-check after stripping the verb — a partially-streamed link
		// could leave a bare URL behind.
		if (looksLikeUrl(s)) return '';
		return s;
	};

	const getExtension = (name: string): string => {
		const idx = name.lastIndexOf('.');
		if (idx <= 0 || idx === name.length - 1) return '';
		return name.slice(idx + 1).toLowerCase();
	};

	const extLabel = (ext: string): string => {
		if (!ext) return $i18n.t('File');
		return ext.toUpperCase();
	};

	type Palette = { bg: string; text: string };

	const palette = (ext: string): Palette => {
		switch (ext) {
			case 'doc':
			case 'docx':
				return {
					bg: 'bg-sky-100 dark:bg-sky-900/40',
					text: 'text-sky-700 dark:text-sky-200'
				};
			case 'xls':
			case 'xlsx':
			case 'csv':
				return {
					bg: 'bg-emerald-100 dark:bg-emerald-900/40',
					text: 'text-emerald-700 dark:text-emerald-200'
				};
			case 'ppt':
			case 'pptx':
				return {
					bg: 'bg-orange-100 dark:bg-orange-900/40',
					text: 'text-orange-700 dark:text-orange-200'
				};
			case 'pdf':
				return {
					bg: 'bg-red-100 dark:bg-red-900/30',
					text: 'text-red-700 dark:text-red-200'
				};
			case 'zip':
			case 'rar':
			case '7z':
			case 'tar':
			case 'gz':
				return {
					bg: 'bg-amber-100 dark:bg-amber-900/30',
					text: 'text-amber-700 dark:text-amber-200'
				};
			case 'png':
			case 'jpg':
			case 'jpeg':
			case 'gif':
			case 'webp':
			case 'svg':
				return {
					bg: 'bg-purple-100 dark:bg-purple-900/30',
					text: 'text-purple-700 dark:text-purple-200'
				};
			case 'json':
			case 'yml':
			case 'yaml':
			case 'xml':
			case 'html':
			case 'css':
			case 'js':
			case 'ts':
			case 'py':
				return {
					bg: 'bg-indigo-100 dark:bg-indigo-900/30',
					text: 'text-indigo-700 dark:text-indigo-200'
				};
			default:
				return {
					bg: 'bg-gray-100 dark:bg-gray-800',
					text: 'text-gray-600 dark:text-gray-300'
				};
		}
	};

	const downloadUrl = (): string => {
		// Always download via /content endpoint
		if (href.includes('/content')) return href;
		if (fileId) return `${WEBUI_API_BASE_URL}/files/${fileId}/content`;
		return href;
	};

	const triggerDownload = () => {
		try {
			const a = document.createElement('a');
			a.href = downloadUrl();
			a.download = displayName || '';
			a.rel = 'noopener noreferrer';
			document.body.appendChild(a);
			a.click();
			a.remove();
		} catch (err) {
			console.error(err);
			toast.error($i18n.t('Failed to download file'));
		}
	};

	const handleClick = (e: MouseEvent) => {
		e.preventDefault();
		triggerDownload();
	};

	const handleDownload = (e: MouseEvent) => {
		e.preventDefault();
		e.stopPropagation();
		triggerDownload();
	};

	// Authoritative filename resolved from the backend (preferred over
	// any fallback text in the markdown link).
	let resolvedApiName: string = '';

	onMount(async () => {
		fileId = extractFileId(href);
		if (fileId) {
			try {
				const user = get(_user);
				if (user?.token) {
					const res = await getFileById(user.token, fileId);
					if (res) {
						fileItem = res;
						const apiName = res?.filename || res?.meta?.name || res?.meta?.filename || '';
						if (apiName) resolvedApiName = apiName;
					}
				}
			} catch (err) {
				// silent fallback: keep using markdown link text
			}
		}
		loading = false;
	});

	// Recompute the display name reactively so that streaming updates to
	// `fallbackName` (e.g. the link label arriving after the URL) are
	// picked up after mount.
	$: cleanedFallback = cleanFallbackName(fallbackName);
	$: displayName = resolvedApiName || cleanedFallback;

	// Keep showing the skeleton/loading state while we don't yet have any
	// usable display name. As soon as we have a clean fallback or an API
	// response we can show the real card. This prevents the raw URL from
	// briefly appearing as the link label during streaming.
	$: isResolving = !displayName && (loading || !done);
	// 流式期间且尚未拿到真实文件名时整体不渲染，避免出现
	// 「卡片骨架 → 原始链接 → 最终卡片」的中间闪烁。等流结束或解析到真实名再淡入。
	$: shouldHide = !done && !displayName;
	$: shownName = displayName || (isResolving ? '' : $i18n.t('Attachment'));
	$: ext = getExtension(shownName);
	$: pal = palette(ext);
	$: sizeBytes = fileItem?.meta?.size ?? fileItem?.size ?? null;
</script>

{#if fileItem}
	<FileItemModal bind:show={showModal} bind:item={fileItem} edit={false} />
{/if}

<span
	class="file-download-card-wrapper file-download-card-enter inline-flex align-middle my-1 mr-1 max-w-full"
	class:hidden={shouldHide}
	aria-hidden={shouldHide ? 'true' : undefined}
>
	{#if shouldHide}
		<!-- 流式中且无真实文件名：占位但不渲染任何可见内容 -->
	{:else if isResolving}
		<!-- Skeleton placeholder shown until we have a real filename or
			streaming finishes. This prevents the raw URL from briefly
			appearing as the link label during streaming. -->
		<span
			class="file-download-card-skeleton inline-flex items-center gap-3 pl-2.5 pr-2 py-2 max-w-full min-w-[16rem]
				rounded-xl border border-gray-200 dark:border-gray-800
				bg-gray-50/70 dark:bg-gray-900/60"
			aria-busy="true"
			aria-label={$i18n.t('Loading...')}
		>
			<span
				class="file-card-badge shrink-0 relative rounded-md flex items-center justify-center bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500"
				style="width: 2rem; height: 2.375rem;"
			>
				<Spinner className="size-4" />
			</span>
			<span class="flex flex-col min-w-0 flex-1 pr-1 leading-tight gap-1.5">
				<span class="skeleton-bar h-3 w-3/5 rounded" />
				<span class="skeleton-bar h-2.5 w-1/3 rounded" />
			</span>
			<span
				class="shrink-0 ml-1 size-7 rounded-lg flex items-center justify-center text-gray-300 dark:text-gray-600"
				aria-hidden="true"
			>
				<Download className="size-4" strokeWidth="2" />
			</span>
		</span>
	{:else}
		<button
			type="button"
			class="group relative inline-flex items-center gap-3 pl-2.5 pr-2 py-2 max-w-full min-w-[16rem]
				rounded-xl border border-gray-200 dark:border-gray-800
				bg-gray-50/70 dark:bg-gray-900/60
				hover:bg-white dark:hover:bg-gray-850
				hover:border-gray-300 dark:hover:border-gray-700
				transition text-left no-underline"
			on:click={handleClick}
			title={shownName}
		>
			<!-- File-type badge: a clean document-shaped chip showing only the extension -->
			<span
				class="file-card-badge shrink-0 relative rounded-md flex items-center justify-center {pal.bg} {pal.text}"
				style="width: 2rem; height: 2.375rem;"
			>
				{#if ext}
					<span class="text-[0.6rem] font-bold leading-none tracking-tight uppercase">
						{ext.length > 4 ? ext.slice(0, 4) : ext}
					</span>
				{:else}
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 24 24"
						fill="currentColor"
						class="size-4 opacity-90"
						aria-hidden="true"
					>
						<path
							fill-rule="evenodd"
							d="M5.625 1.5c-1.036 0-1.875.84-1.875 1.875v17.25c0 1.035.84 1.875 1.875 1.875h12.75c1.035 0 1.875-.84 1.875-1.875V12.75A3.75 3.75 0 0 0 16.5 9h-1.875a1.875 1.875 0 0 1-1.875-1.875V5.25A3.75 3.75 0 0 0 9 1.5H5.625Z"
							clip-rule="evenodd"
						/>
						<path
							d="M12.971 1.816A5.23 5.23 0 0 1 14.25 5.25v1.875c0 .207.168.375.375.375H16.5a5.23 5.23 0 0 1 3.434 1.279 9.768 9.768 0 0 0-6.963-6.963Z"
						/>
					</svg>
				{/if}
			</span>

			<!-- File info -->
			<span class="flex flex-col min-w-0 flex-1 pr-1 leading-tight gap-0.5">
				<span
					class="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-1 break-all"
				>
					{shownName}
				</span>
				<span class="text-[0.7rem] text-gray-500 dark:text-gray-400 line-clamp-1 font-normal">
					{extLabel(ext)}{#if sizeBytes}
						<span class="mx-1">·</span>{formatFileSize(sizeBytes)}
					{/if}
				</span>
			</span>

			<!-- Download button -->
			<Tooltip content={$i18n.t('Download')}>
				<span
					class="shrink-0 ml-1 size-7 rounded-lg flex items-center justify-center
						text-gray-500 dark:text-gray-400
						hover:bg-gray-100 dark:hover:bg-gray-800
						hover:text-gray-900 dark:hover:text-white transition"
					role="button"
					tabindex="0"
					on:click={handleDownload}
					on:keydown={(e) => {
						if (e.key === 'Enter' || e.key === ' ') {
							e.preventDefault();
							handleDownload(e);
						}
					}}
				>
					<Download className="size-4" strokeWidth="2" />
				</span>
			</Tooltip>
		</button>
	{/if}
</span>

<style>
	.file-download-card-wrapper :global(button) {
		text-decoration: none !important;
	}
	.file-download-card-wrapper {
		/* Prevent prose styles from underlining the inner content */
		text-decoration: none !important;
	}

	/* Subtle fade/scale-in so the card doesn't pop in abruptly during streaming */
	.file-download-card-enter {
		animation: fileCardIn 180ms ease-out both;
	}
	@keyframes fileCardIn {
		from {
			opacity: 0;
			transform: translateY(2px) scale(0.98);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	/* Document-shaped badge with a folded top-right corner */
	.file-card-badge {
		clip-path: polygon(0 0, calc(100% - 7px) 0, 100% 7px, 100% 100%, 0 100%);
	}
	.file-card-badge::after {
		content: '';
		position: absolute;
		top: 0;
		right: 0;
		width: 7px;
		height: 7px;
		background: rgba(0, 0, 0, 0.08);
		clip-path: polygon(0 0, 100% 100%, 100% 0);
	}
	:global(.dark) .file-card-badge::after {
		background: rgba(255, 255, 255, 0.1);
	}

	/* Skeleton placeholder bars while waiting for the real filename */
	.skeleton-bar {
		display: inline-block;
		background: linear-gradient(
			90deg,
			rgba(0, 0, 0, 0.06) 0%,
			rgba(0, 0, 0, 0.12) 50%,
			rgba(0, 0, 0, 0.06) 100%
		);
		background-size: 200% 100%;
		animation: skeletonShimmer 1.2s ease-in-out infinite;
	}
	:global(.dark) .skeleton-bar {
		background: linear-gradient(
			90deg,
			rgba(255, 255, 255, 0.06) 0%,
			rgba(255, 255, 255, 0.14) 50%,
			rgba(255, 255, 255, 0.06) 100%
		);
		background-size: 200% 100%;
	}
	@keyframes skeletonShimmer {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}
</style>
