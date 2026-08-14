<script lang="ts">
	import { onMount, onDestroy, getContext, tick } from 'svelte';
	import { page } from '$app/stores';

	import {
		getLightningPushes,
		getLightningPushImageUrl,
		type LightningPushSummary,
		type LightningJumpEventModel
	} from '$lib/apis/monitoring';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import ImagePreview from '$lib/components/common/ImagePreview.svelte';

	const i18n = getContext('i18n');

	type FlatEvent = {
		push: LightningPushSummary;
		event: LightningJumpEventModel;
	};

	// 临时兜底样例数据：接口/网络异常拿不到真实数据时，先用这条把页面样式展示出来，
	// 方便预览效果。等真实数据链路稳定后，这段可以整段删掉（连同下面的 DEMO_PUSH_ID 判断）。
	const DEMO_PUSH_ID = 'demo-push-1';
	const FALLBACK_PUSH: LightningPushSummary = {
		id: DEMO_PUSH_ID,
		push_time: new Date(2026, 6, 26, 16, 13, 0).getTime() * 1_000_000,
		coverage_start: new Date(2026, 6, 26, 16, 6, 0).getTime() * 1_000_000,
		coverage_end: new Date(2026, 6, 26, 16, 6, 0).getTime() * 1_000_000,
		csv_path: 'demo',
		json_path: null,
		png_path: 'demo',
		created_at: 0,
		event_count: 1,
		events: [
			{
				id: 'demo-event-1',
				push_id: DEMO_PUSH_ID,
				cell_seq: '1',
				region: '沧州市黄骅市；沧州市孟村回族自治县',
				jump_times: '15:52',
				created_at: 0
			}
		]
	};

	const imageSrcFor = (push: LightningPushSummary) =>
		push.id === DEMO_PUSH_ID ? '/demo/lightning-sample.png' : getLightningPushImageUrl(push.id);

	let loading = true;
	let refreshing = false;
	let pushes: LightningPushSummary[] = [];
	let flatEvents: FlatEvent[] = [];

	let selectedPushId: string | null = null;
	let highlightEventId: string | null = null;
	let showFullscreen = false;

	let refreshTimer: ReturnType<typeof setInterval> | null = null;

	// 中文日期时间格式：X月X日X时X分（例如 7月26日16时06分）。
	const formatChineseTime = (ns: number | null) => {
		if (!ns) return '--';
		const d = new Date(ns / 1_000_000);
		const pad = (n: number) => String(n).padStart(2, '0');
		return `${d.getMonth() + 1}月${d.getDate()}日${pad(d.getHours())}时${pad(d.getMinutes())}分`;
	};

	// 地区用"；"分隔、跳增时刻用";"分隔，两边数量不一定相等（同一单体可能只给一个时刻
	// 但影响了好几个区县），按下标配对，多出来的地区复用最后一个时刻。
	const regionJumpPairs = (event: LightningJumpEventModel) => {
		const regions = (event.region || '')
			.split('；')
			.map((r) => r.trim())
			.filter(Boolean);
		const times = (event.jump_times || '')
			.split(';')
			.map((t) => t.trim())
			.filter(Boolean);
		return regions.map((region, i) => ({
			region,
			time: times[i] ?? times[times.length - 1] ?? '--'
		}));
	};

	$: selectedPush = pushes.find((p) => p.id === selectedPushId) ?? null;

	const load = async (targetPushId?: string | null) => {
		refreshing = true;
		try {
			const res = await getLightningPushes(localStorage.token, { limit: 40 });
			pushes = res.items;

			const flat: FlatEvent[] = [];
			for (const push of pushes) {
				for (const event of push.events) {
					flat.push({ push, event });
				}
			}
			flatEvents = flat;

			if (targetPushId && pushes.some((p) => p.id === targetPushId)) {
				selectedPushId = targetPushId;
			} else if (!selectedPushId && pushes.length > 0) {
				selectedPushId = pushes[0].id;
			}
		} catch (e) {
			console.error(e);
		}

		if (!pushes || pushes.length === 0) {
			// 临时兜底，见上方 FALLBACK_PUSH 注释。
			pushes = [FALLBACK_PUSH];
			flatEvents = FALLBACK_PUSH.events.map((event) => ({ push: FALLBACK_PUSH, event }));
			if (!selectedPushId) selectedPushId = FALLBACK_PUSH.id;
		}

		loading = false;
		refreshing = false;
	};

	const selectEvent = async (item: FlatEvent) => {
		selectedPushId = item.push.id;
		highlightEventId = item.event.id;
	};

	onMount(async () => {
		const pushIdParam = $page.url.searchParams.get('push_id');
		const eventIdParam = $page.url.searchParams.get('event_id');
		highlightEventId = eventIdParam;

		await load(pushIdParam);

		if (eventIdParam) {
			await tick();
			const el = document.getElementById(`lightning-event-${eventIdParam}`);
			if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
		}

		refreshTimer = setInterval(() => load(), 60_000);
	});

	onDestroy(() => {
		if (refreshTimer) clearInterval(refreshTimer);
	});
</script>

<div class="flex flex-1 min-h-0 gap-3">
	{#if loading}
		<div class="flex-1 flex items-center justify-center">
			<Spinner />
		</div>
	{:else}
		<!-- 左侧：跳增事件列表 -->
		<div
			class="w-64 shrink-0 flex flex-col rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden"
		>
			<div
				class="flex items-center justify-between px-3 py-2 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-800"
			>
				<span>{$i18n.t('Recent Events')}</span>
				<button
					class="hover:text-gray-600 dark:hover:text-gray-300 {refreshing ? 'animate-pulse' : ''}"
					on:click={() => load()}
				>
					{$i18n.t('Refresh')}
				</button>
			</div>
			<div class="flex-1 overflow-y-auto scrollbar-thin">
				{#if flatEvents.length === 0}
					<div class="flex items-center justify-center py-12 text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t('No data available yet')}
					</div>
				{:else}
					{#each flatEvents as item (item.event.id)}
						<button
							id={`lightning-event-${item.event.id}`}
							class="w-full text-left px-3 py-2 border-b border-gray-50 dark:border-gray-850 transition {selectedPushId ===
								item.push.id && highlightEventId === item.event.id
								? 'bg-amber-50 dark:bg-amber-900/20'
								: selectedPushId === item.push.id
									? 'bg-gray-50 dark:bg-gray-850/60'
									: 'hover:bg-gray-50 dark:hover:bg-gray-850/60'}"
							on:click={() => selectEvent(item)}
						>
							<div class="text-xs text-gray-400 dark:text-gray-500">
								{formatChineseTime(item.push.coverage_start ?? item.push.push_time)}
							</div>
							<div class="flex flex-col gap-0.5 mt-0.5">
								{#each regionJumpPairs(item.event) as pair}
									<div class="text-sm leading-snug">
										<span>{pair.region}</span>
										<span class="text-xs text-amber-600 dark:text-amber-400"
											>· {$i18n.t('Jump Time')} {pair.time}</span
										>
									</div>
								{/each}
							</div>
						</button>
					{/each}
				{/if}
			</div>
		</div>

		<!-- 右侧：选中推送的 PNG 大图 -->
		<div
			class="flex-1 min-w-0 flex flex-col rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden"
		>
			<div class="flex-1 min-h-0 flex items-center justify-center p-3 overflow-auto">
				{#if selectedPush?.png_path}
					<button
						class="max-w-full max-h-full cursor-zoom-in"
						on:click={() => (showFullscreen = true)}
					>
						<img
							src={imageSrcFor(selectedPush)}
							alt={$i18n.t('Lightning Jump Warning')}
							class="max-w-full max-h-full object-contain rounded-lg"
						/>
					</button>
				{:else}
					<div class="text-sm text-gray-400 dark:text-gray-500">
						{$i18n.t('No data available yet')}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

{#if selectedPush?.png_path}
	<ImagePreview
		bind:show={showFullscreen}
		src={imageSrcFor(selectedPush)}
		alt={$i18n.t('Lightning Jump Warning')}
	/>
{/if}
