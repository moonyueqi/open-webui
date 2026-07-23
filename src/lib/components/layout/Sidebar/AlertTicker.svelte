<script lang="ts">
	import { onMount, onDestroy, getContext, createEventDispatcher } from 'svelte';
	import { fly, slide } from 'svelte/transition';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	// 预警消息列表（后续接入真实数据时替换这里）
	// level: 'info' | 'warning' | 'danger'，用于文字颜色
	// target: 后续要跳转到的监测预警栏目路径，例如 '/monitoring/ground'（当前数据未就绪，先不跳转）
	export let alerts: { id: string; text: string; level?: string; target?: string }[] = [
		{
			id: 'demo-1',
			text: '示例：地面监测站点风速偏高，请关注',
			level: 'warning',
			target: '/monitoring/ground'
		},
		{
			id: 'demo-2',
			text: '示例：高空温度骤降，注意后续变化',
			level: 'info',
			target: '/monitoring/upper-air'
		},
		{
			id: 'demo-3',
			text: '示例：局地能见度下降，达到预警阈值',
			level: 'danger',
			target: '/monitoring/ground'
		},
		{
			id: 'demo-4',
			text: '示例：地面湿度异常升高，请核查设备',
			level: 'warning',
			target: '/monitoring/ground'
		},
		{
			id: 'demo-5',
			text: '示例：高空气压变化明显，持续观察',
			level: 'info',
			target: '/monitoring/upper-air'
		}
	];

	// 单条停留时长（毫秒）
	export let interval = 4000;

	// 已读消息的 id 集合
	let readIds = new Set<string>();
	// 是否展开未读消息列表
	let expanded = false;

	let currentIndex = 0;
	let timer: ReturnType<typeof setInterval> | null = null;
	let paused = false;

	// 未读消息（播报与列表都基于它）
	$: unread = (alerts ?? []).filter((a) => !readIds.has(a.id));
	$: unreadCount = unread.length;

	// 保证 currentIndex 始终落在有效范围内
	$: if (currentIndex >= unread.length) {
		currentIndex = 0;
	}
	$: current = unread[currentIndex] ?? null;

	const levelClass = (level?: string) => {
		switch (level) {
			case 'danger':
				return 'text-red-600 dark:text-red-400';
			case 'warning':
				return 'text-amber-600 dark:text-amber-400';
			default:
				return 'text-sky-600 dark:text-sky-400';
		}
	};

	const dotClass = (level?: string) => {
		switch (level) {
			case 'danger':
				return 'bg-red-500';
			case 'warning':
				return 'bg-amber-500';
			default:
				return 'bg-sky-500';
		}
	};

	const next = () => {
		if (unread.length === 0) return;
		currentIndex = (currentIndex + 1) % unread.length;
	};

	const startTimer = () => {
		stopTimer();
		timer = setInterval(() => {
			if (!paused && !expanded && unread.length > 1) next();
		}, interval);
	};

	const stopTimer = () => {
		if (timer) {
			clearInterval(timer);
			timer = null;
		}
	};

	const markAsRead = (alert: { id: string; target?: string } | null) => {
		if (!alert) return;
		readIds = new Set(readIds).add(alert.id);
		dispatch('read', { id: alert.id });

		// 监测预警各栏目数据尚未就绪，暂不跳转。
		// 待数据接入后，可在此处使用 goto(alert.target) 跳转到对应栏目。
	};

	const markAllAsRead = () => {
		const next = new Set(readIds);
		for (const a of unread) next.add(a.id);
		readIds = next;
		dispatch('readAll');
	};

	const toggleExpanded = () => {
		expanded = !expanded;
	};

	onMount(() => {
		startTimer();
	});

	onDestroy(() => {
		stopTimer();
	});
</script>

<div class="px-[0.4375rem]">
	<div
		class="rounded-lg border border-gray-200/70 dark:border-gray-800/70 bg-white dark:bg-gray-900 overflow-hidden"
		role="region"
		aria-label={$i18n.t('Alerts')}
		on:mouseenter={() => (paused = true)}
		on:mouseleave={() => (paused = false)}
	>
		<!-- 标题栏：点击展开/收起未读列表 -->
		<button
			type="button"
			class="w-full flex items-center gap-1.5 px-2.5 pt-1.5 pb-1 text-[0.6875rem] font-medium text-gray-400 dark:text-gray-500 select-none hover:text-gray-600 dark:hover:text-gray-300 transition"
			on:click={toggleExpanded}
			aria-expanded={expanded}
		>
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="size-3">
				<path
					fill-rule="evenodd"
					d="M5.25 9a6.75 6.75 0 0 1 13.5 0v.75c0 2.123.8 4.057 2.118 5.52a.75.75 0 0 1-.297 1.206c-1.544.57-3.16.99-4.831 1.243a3.75 3.75 0 1 1-7.48 0 24.585 24.585 0 0 1-4.831-1.244.75.75 0 0 1-.298-1.205A8.217 8.217 0 0 0 5.25 9.75V9Zm4.502 8.9a2.25 2.25 0 1 0 4.496 0 25.057 25.057 0 0 1-4.496 0Z"
					clip-rule="evenodd"
				/>
			</svg>
			<span>{$i18n.t('Alerts')}</span>

			{#if unreadCount > 0}
				<span
					class="ml-0.5 min-w-4 h-4 px-1 inline-flex items-center justify-center rounded-full bg-red-500 text-white text-[0.625rem] font-semibold leading-none"
				>
					{unreadCount > 99 ? '99+' : unreadCount}
				</span>
			{/if}

			<span class="grow"></span>

			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 20 20"
				fill="currentColor"
				class="size-3.5 transition-transform duration-200 {expanded ? 'rotate-180' : ''}"
			>
				<path
					fill-rule="evenodd"
					d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.168l3.71-3.938a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
					clip-rule="evenodd"
				/>
			</svg>
		</button>

		{#if expanded}
			<!-- 展开：未读消息全部列表（带滚动） -->
			<div transition:slide={{ duration: 200 }}>
				<div class="max-h-56 overflow-y-auto scrollbar-thin px-1.5 pb-1.5">
					{#if unreadCount === 0}
						<div class="px-1.5 py-3 text-center text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('No unread alerts')}
						</div>
					{:else}
						{#each unread as alert (alert.id)}
							<button
								type="button"
								class="w-full flex items-start gap-1.5 px-2 py-1.5 rounded-md text-left hover:bg-gray-100 dark:hover:bg-gray-800/60 transition group"
								on:click={() => markAsRead(alert)}
								title={$i18n.t('Click to mark as read')}
							>
								<span
									class="size-1.5 mt-1.5 rounded-full flex-shrink-0 {dotClass(alert.level)}"
								></span>
								<span class="text-xs leading-snug flex-1 {levelClass(alert.level)}">
									{alert.text}
								</span>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 20 20"
									fill="currentColor"
									class="size-3.5 mt-0.5 flex-shrink-0 text-gray-300 dark:text-gray-600 opacity-0 group-hover:opacity-100 transition"
								>
									<path
										fill-rule="evenodd"
										d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
										clip-rule="evenodd"
									/>
								</svg>
							</button>
						{/each}
					{/if}
				</div>

				{#if unreadCount > 0}
					<div class="border-t border-gray-200/60 dark:border-gray-800/60 px-1.5 py-1">
						<button
							type="button"
							class="w-full text-center text-[0.6875rem] py-1 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/60 transition"
							on:click={markAllAsRead}
						>
							{$i18n.t('Mark all as read')}
						</button>
					</div>
				{/if}
			</div>
		{:else}
			<!-- 收起：单条轮播播报 -->
			<div class="relative h-8 overflow-hidden">
				{#if current}
					{#key current.id}
						<button
							type="button"
							class="absolute inset-0 w-full flex items-center gap-1.5 px-2.5 pb-1.5 text-left cursor-pointer"
							on:click={() => markAsRead(current)}
							title={$i18n.t('Click to mark as read')}
							in:fly={{ y: 12, duration: 300 }}
							out:fly={{ y: -12, duration: 300 }}
						>
							<span class="size-1.5 rounded-full flex-shrink-0 {dotClass(current.level)}"></span>
							<span class="text-xs truncate {levelClass(current.level)}" title={current.text}>
								{current.text}
							</span>
						</button>
					{/key}
				{:else}
					<div
						class="absolute inset-0 w-full flex items-center px-2.5 pb-1.5 text-xs text-gray-400 dark:text-gray-500"
					>
						{$i18n.t('No unread alerts')}
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>
