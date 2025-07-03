/**
 * K线图页面JavaScript功能模块
 * 包含图表交互、事件处理、标记点生成等功能
 */

// 全局变量
let originalMarkPoints = null;

/**
 * 图表工具类
 */
class ChartUtils {
    /**
     * 获取ECharts实例
     * @returns {Object|null} ECharts实例或null
     */
    static getEChartsInstance() {
        const container = document.getElementById('kline-chart');
        if (!container) {
            console.warn('未找到图表容器 #kline-chart');
            return null;
        }
    
        // 方法1：尝试通过_echarts_instance_属性查找
        let chartContainer = container.querySelector('div[_echarts_instance_]');
        if (chartContainer && chartContainer._echarts_instance_) {
            const instance = echarts.getInstanceByDom(chartContainer);
            if (instance) {
                console.log('通过_echarts_instance_属性找到ECharts实例');
                return instance;
            }
        }
    
        // 方法2：遍历所有div元素，查找ECharts实例
        const allDivs = container.querySelectorAll('div');
        for (let div of allDivs) {
            const instance = echarts.getInstanceByDom(div);
            if (instance) {
                console.log('通过遍历div元素找到ECharts实例');
                return instance;
            }
        }
    
        // 方法3：通过canvas元素查找父div
        const canvasElements = container.querySelectorAll('canvas');
        for (let canvas of canvasElements) {
            let parent = canvas.parentElement;
            while (parent && parent !== container) {
                const instance = echarts.getInstanceByDom(parent);
                if (instance) {
                    console.log('通过canvas父元素找到ECharts实例');
                    return instance;
                }
                parent = parent.parentElement;
            }
        }
    
        // 方法4：尝试通过全局echarts对象获取所有实例
        if (typeof echarts !== 'undefined' && echarts.getInstanceByDom) {
            // 查找容器内所有可能的图表元素
            const possibleChartElements = container.querySelectorAll('div[style*="position"], div[style*="width"], div[style*="height"]');
            for (let element of possibleChartElements) {
                const instance = echarts.getInstanceByDom(element);
                if (instance) {
                    console.log('通过样式特征找到ECharts实例');
                    return instance;
                }
            }
        }
    
        // 方法5：最后尝试直接在容器上查找
        if (typeof echarts !== 'undefined') {
            const instance = echarts.getInstanceByDom(container);
            if (instance) {
                console.log('直接在容器上找到ECharts实例');
                return instance;
            }
        }
    
        console.warn('未找到ECharts实例，可能的原因：');
        console.warn('1. 图表还未完全加载');
        console.warn('2. pyecharts生成的HTML结构发生变化');
        console.warn('3. ECharts库加载失败');
        console.warn('4. 图表容器结构异常');
        
        // 调试信息
        console.log('容器内容：', container.innerHTML.substring(0, 500));
        console.log('ECharts是否可用：', typeof echarts !== 'undefined');
        
        return null;
    }

    /**
     * 滚动K线图到指定日期位置
     * @param {string} eventDate - 事件日期
     * @param {Object} chartInstance - ECharts实例
     */
    static scrollToDate(eventDate, chartInstance) {
        if (!eventDate || !chartInstance) return;
        
        const option = chartInstance.getOption();
        const xAxisData = option.xAxis[0].data;
        const eventIndex = xAxisData.findIndex(date => date === eventDate);
        
        if (eventIndex !== -1) {
            const totalDataPoints = xAxisData.length;
            const eventPercentage = (eventIndex / (totalDataPoints - 1)) * 100;
            const zoomRange = 20;
            const startPercentage = Math.max(0, eventPercentage - zoomRange / 2);
            const endPercentage = Math.min(100, eventPercentage + zoomRange / 2);
            
            chartInstance.setOption({
                dataZoom: [{
                    type: 'inside',
                    start: startPercentage,
                    end: endPercentage
                }, {
                    type: 'slider',
                    start: startPercentage,
                    end: endPercentage
                }]
            });
        }
    }
}

/**
 * 标记点生成器
 */
class MarkPointGenerator {
    /**
     * 生成标记点数据
     * @param {NodeList} events - 事件DOM元素列表
     * @param {Object} chartInstance - ECharts实例
     * @returns {Array} 标记点数据数组
     */
    static generateMarkPointData(events, chartInstance) {
        const markPoints = [];
        
        if (!chartInstance || !events || events.length === 0) {
            return [];
        }
        
        try {
            const option = chartInstance.getOption();
            if (!option || !option.xAxis || !option.xAxis[0] || !option.xAxis[0].data) {
                return [];
            }
            
            const seriesData = option.series[0].data;
            if (!seriesData || seriesData.length === 0) {
                return [];
            }
            
            // 按日期分组事件
            const eventsByDate = this._groupEventsByDate(events);
            
            // 为每个日期的事件生成标记点
            Object.keys(eventsByDate).forEach(eventDate => {
                const dailyEvents = eventsByDate[eventDate];
                const { candleHigh, matchedKlineDate } = this._findMatchingKlineData(eventDate, seriesData);
                
                if (candleHigh !== null) {
                    const verticalOffsetIncrement = this._calculateVerticalOffset(seriesData, candleHigh);
                    this._createMarkPointsForDate(dailyEvents, matchedKlineDate, candleHigh, verticalOffsetIncrement, markPoints);
                }
            });
            
            return markPoints;
        } catch (error) {
            console.error('生成标记点数据时出错:', error);
            return [];
        }
    }

    /**
     * 按日期分组事件
     * @param {NodeList} events - 事件DOM元素列表
     * @returns {Object} 按日期分组的事件对象
     */
    static _groupEventsByDate(events) {
        const eventsByDate = {};
        events.forEach(function(event) {
            const eventDate = event.getAttribute('data-event-date');
            if (eventDate) {
                if (!eventsByDate[eventDate]) {
                    eventsByDate[eventDate] = [];
                }
                eventsByDate[eventDate].push(event);
            }
        });
        return eventsByDate;
    }

    /**
     * 查找匹配的K线数据
     * @param {string} eventDate - 事件日期
     * @param {Array} seriesData - K线数据
     * @returns {Object} 包含candleHigh和matchedKlineDate的对象
     */
    static _findMatchingKlineData(eventDate, seriesData) {
        let candleHigh = null;
        let matchedKlineDate = null;
        
        const eventTimestamp = new Date(eventDate).getTime();
        
        for (let i = 0; i < seriesData.length; i++) {
            const klineDate = seriesData[i][0];
            let klineTimestamp;
            
            if (typeof klineDate === 'number') {
                if (klineDate > 1000000000000) {
                    klineTimestamp = klineDate;
                } else if (klineDate > 1000000000) {
                    klineTimestamp = klineDate * 1000;
                } else {
                    const excelEpoch = new Date(1900, 0, 1).getTime();
                    klineTimestamp = excelEpoch + (klineDate - 1) * 24 * 60 * 60 * 1000;
                }
            } else if (typeof klineDate === 'string') {
                klineTimestamp = new Date(klineDate).getTime();
            } else {
                continue;
            }
            
            if (Math.abs(klineTimestamp - eventTimestamp) < 24 * 60 * 60 * 1000) {
                candleHigh = seriesData[i][3];
                matchedKlineDate = klineDate;
                break;
            }
        }
        
        return { candleHigh, matchedKlineDate };
    }

    /**
     * 计算垂直偏移量
     * @param {Array} seriesData - K线数据
     * @param {number} candleHigh - 蜡烛最高价
     * @returns {number} 垂直偏移增量
     */
    static _calculateVerticalOffset(seriesData, candleHigh) {
        let minPrice = Infinity;
        let maxPrice = -Infinity;
        
        seriesData.forEach(data => {
            const high = data[3];
            const low = data[2];
            if (high > maxPrice) maxPrice = high;
            if (low < minPrice) minPrice = low;
        });
        
        const priceRange = maxPrice - minPrice;
        let verticalOffsetIncrement = priceRange * 0.01;
        
        if (verticalOffsetIncrement === 0) {
            verticalOffsetIncrement = candleHigh * 0.01 > 0 ? candleHigh * 0.01 : 0.1;
        }
        
        return verticalOffsetIncrement;
    }

    /**
     * 为指定日期创建标记点
     * @param {Array} dailyEvents - 当日事件列表
     * @param {string} matchedKlineDate - 匹配的K线日期
     * @param {number} candleHigh - 蜡烛最高价
     * @param {number} verticalOffsetIncrement - 垂直偏移增量
     * @param {Array} markPoints - 标记点数组
     */
    static _createMarkPointsForDate(dailyEvents, matchedKlineDate, candleHigh, verticalOffsetIncrement, markPoints) {
        dailyEvents.forEach((item, index) => {
            const eventId = item.getAttribute('data-event-id');
            const starYCoord = candleHigh + (verticalOffsetIncrement * (index + 1));
            
            markPoints.push({
                name: eventId,
                coord: [matchedKlineDate, starYCoord],
                symbol: 'path://M8,0 L10.472,5.236 L16,6.18 L11.764,9.818 L13.056,15 L8,12.273 L2.944,15 L4.236,9.818 L0,6.18 L5.528,5.236 Z',
                symbolSize: 15,
                itemStyle: {
                    color: 'gold'
                },
                label: {
                    show: false
                }
            });
        });
    }
}

/**
 * 事件处理器
 */
class EventHandler {
    /**
     * 初始化事件列表交互
     * @param {Object} chartInstance - ECharts实例
     */
    static initializeEventListInteractions(chartInstance) {
        const eventListItems = document.querySelectorAll('#event-list .event-item');
        
        eventListItems.forEach(function(item) {
            // 点击事件
            item.addEventListener('click', function() {
                EventHandler._handleEventItemClick(this, chartInstance);
            });
            
            // 鼠标悬浮事件
            item.addEventListener('mouseenter', function() {
                EventHandler._handleEventItemMouseEnter(this, chartInstance);
            });
            
            // 鼠标离开事件
            item.addEventListener('mouseleave', function() {
                EventHandler._handleEventItemMouseLeave(chartInstance);
            });
            
            // 设置鼠标样式
            item.style.cursor = 'pointer';
        });
    }

    /**
     * 处理事件项点击
     * @param {Element} element - 被点击的事件元素
     * @param {Object} chartInstance - ECharts实例
     */
    static _handleEventItemClick(element, chartInstance) {
        const eventId = element.getAttribute('data-event-id');
        const eventDate = element.getAttribute('data-event-date');
        
        // 滚动K线图到对应位置
        ChartUtils.scrollToDate(eventDate, chartInstance);
        
        // 在新标签页打开事件链接
        if (window.eventsData && window.eventsData.length > 0) {
            const event = window.eventsData.find(e => e && e.id && e.id.toString() === eventId);
            if (event && event.source_url) {
                window.open(event.source_url, '_blank');
            }
        }
    }

    /**
     * 处理事件项鼠标悬浮
     * @param {Element} element - 悬浮的事件元素
     * @param {Object} chartInstance - ECharts实例
     */
    static _handleEventItemMouseEnter(element, chartInstance) {
        const eventDate = element.getAttribute('data-event-date');
        const eventId = element.getAttribute('data-event-id');
        
        // 滚动K线图到对应位置
        ChartUtils.scrollToDate(eventDate, chartInstance);
        
        // 高亮星星
        this._highlightStar(eventId, chartInstance);
    }

    /**
     * 处理事件项鼠标离开
     * @param {Object} chartInstance - ECharts实例
     */
    static _handleEventItemMouseLeave(chartInstance) {
        this._restoreOriginalMarkPoints(chartInstance);
    }

    /**
     * 高亮指定的星星
     * @param {string} eventId - 事件ID
     * @param {Object} chartInstance - ECharts实例
     */
    static _highlightStar(eventId, chartInstance) {
        if (!chartInstance) return;
        
        const visibleEvents = document.querySelectorAll('.event-item:not([style*="display: none"])');
        const currentOption = chartInstance.getOption();
        let backupMarkPoints = [];
        
        if (currentOption.series && currentOption.series[0] && currentOption.series[0].markPoint) {
            backupMarkPoints = JSON.parse(JSON.stringify(currentOption.series[0].markPoint.data));
        }
        
        const markPoints = MarkPointGenerator.generateMarkPointData(visibleEvents, chartInstance);
        
        if (markPoints.length === 0 && backupMarkPoints.length > 0) {
            const highlightedMarkPoints = backupMarkPoints.map(function(point) {
                if (point.name === eventId) {
                    return {
                        ...point,
                        itemStyle: { color: 'red' },
                        symbolSize: 20
                    };
                }
                return point;
            });
            
            chartInstance.setOption({
                series: [{ markPoint: { data: highlightedMarkPoints } }]
            });
            return;
        }
        
        const highlightedMarkPoints = markPoints.map(function(point) {
            if (point.name === eventId) {
                return {
                    ...point,
                    itemStyle: { color: 'red' },
                    symbolSize: 20
                };
            }
            return point;
        });

        // 添加高亮区域
        const markAreaData = [];
        const highlighted = highlightedMarkPoints.some(point => 
            point.name === eventId && point.itemStyle && point.itemStyle.color === 'red'
        );
        
        if (highlighted) {
            const eventDate = document.querySelector(`[data-event-id="${eventId}"]`)?.getAttribute('data-event-date');
            if (eventDate) {
                markAreaData.push([{
                    xAxis: eventDate,
                    itemStyle: { color: 'rgba(255, 223, 186, 0.3)' }
                }, {
                    xAxis: eventDate
                }]);
            }
        }
        
        chartInstance.setOption({
            series: [{
                markPoint: { data: highlightedMarkPoints },
                markArea: { silent: true, data: markAreaData }
            }]
        });
    }

    /**
     * 恢复原始标记点状态
     * @param {Object} chartInstance - ECharts实例
     */
    static _restoreOriginalMarkPoints(chartInstance) {
        if (chartInstance && originalMarkPoints && originalMarkPoints.length > 0) {
            chartInstance.setOption({
                series: [{
                    markPoint: { data: originalMarkPoints },
                    markArea: { data: [] }
                }]
            });
        } else {
            ChartManager.updateChartMarkPoints();
            if (chartInstance) {
                chartInstance.setOption({
                    series: [{ markArea: { data: [] } }]
                });
            }
        }
    }

    /**
     * 初始化图表星星交互
     * @param {Object} chartInstance - ECharts实例
     */
    static initializeChartStarInteractions(chartInstance) {
        // 星星悬浮事件
        chartInstance.on('mouseover', function(params) {
            if (params.componentType === 'markPoint' && params.data && params.data.name) {
                EventHandler._handleStarMouseOver(params.data.name, chartInstance);
            }
        });
        
        // 星星鼠标离开事件
        chartInstance.on('mouseout', function(params) {
            if (params.componentType === 'markPoint') {
                EventHandler._handleStarMouseOut(chartInstance);
            }
        });
    }

    /**
     * 处理星星鼠标悬浮
     * @param {string} eventId - 事件ID
     * @param {Object} chartInstance - ECharts实例
     */
    static _handleStarMouseOver(eventId, chartInstance) {
        // 高亮对应的事件列表项并滚动到可视区域
        const eventListItems = document.querySelectorAll('#event-list .event-item');
        eventListItems.forEach(function(item) {
            const itemEventId = item.getAttribute('data-event-id');
            if (itemEventId && eventId === itemEventId) {
                item.style.backgroundColor = '#ffeb3b';
                item.style.fontWeight = 'bold';
                
                // 滚动到可视区域
                const eventListContainer = document.querySelector('.events-list');
                const itemRect = item.getBoundingClientRect();
                const containerRect = eventListContainer.getBoundingClientRect();
                
                if (itemRect.top < containerRect.top || itemRect.bottom > containerRect.bottom) {
                    const itemOffsetTop = item.offsetTop;
                    const containerHeight = eventListContainer.clientHeight;
                    const itemHeight = item.offsetHeight;
                    const targetScrollTop = itemOffsetTop - (containerHeight / 2) + (itemHeight / 2);
                    
                    eventListContainer.scrollTo({
                        top: Math.max(0, targetScrollTop),
                        behavior: 'smooth'
                    });
                }
            }
        });
        
        // 修改星星颜色为红色
        if (originalMarkPoints && originalMarkPoints.length > 0) {
            const highlightedMarkPoints = originalMarkPoints.map(function(point) {
                if (point.name === eventId) {
                    return {
                        ...point,
                        itemStyle: { color: 'red' },
                        symbolSize: 20
                    };
                }
                return point;
            });
            
            chartInstance.setOption({
                series: [{ markPoint: { data: highlightedMarkPoints } }]
            });
        }
    }

    /**
     * 处理星星鼠标离开
     * @param {Object} chartInstance - ECharts实例
     */
    static _handleStarMouseOut(chartInstance) {
        // 恢复事件列表项的样式
        const eventListItems = document.querySelectorAll('#event-list .event-item');
        eventListItems.forEach(function(item) {
            item.style.backgroundColor = '';
            item.style.fontWeight = '';
        });
        
        // 恢复到原始标记点状态
        if (originalMarkPoints && originalMarkPoints.length > 0) {
            chartInstance.setOption({
                series: [{ markPoint: { data: originalMarkPoints } }]
            });
        } else {
            ChartManager.updateChartMarkPoints();
        }
    }
}

/**
 * 图表管理器
 */
class ChartManager {
    /**
     * 更新K线图上的标记点
     */
    static updateChartMarkPoints() {
        const chartInstance = ChartUtils.getEChartsInstance();
        if (!chartInstance) return;
        
        const visibleEvents = document.querySelectorAll('.event-item:not([style*="display: none"])');
        const markPoints = MarkPointGenerator.generateMarkPointData(visibleEvents, chartInstance);
        
        if (markPoints && markPoints.length > 0) {
            chartInstance.setOption({
                series: [{ markPoint: { data: markPoints } }]
            });
        }
    }

    /**
     * 初始化图表交互
     * @param {Object} chartInstance - ECharts实例
     */
    static initializeChartInteractions(chartInstance) {
        // 获取原始配置
        const originalOption = chartInstance.getOption();
        
        if (originalOption.series && originalOption.series[0] && originalOption.series[0].markPoint) {
            originalMarkPoints = JSON.parse(JSON.stringify(originalOption.series[0].markPoint.data));
        } else {
            console.warn('未找到原始标记点数据');
            return;
        }

        // 初始化事件列表交互
        EventHandler.initializeEventListInteractions(chartInstance);
        
        // 初始化图表星星交互
        EventHandler.initializeChartStarInteractions(chartInstance);
    }
}

/**
 * 应用初始化
 */
class App {
    /**
     * 初始化应用 - 改进版本
     */
    static init() {
        document.addEventListener('DOMContentLoaded', function() {
            // 等待更长时间，确保pyecharts图表完全渲染
            setTimeout(function() {
                const chartInstance = ChartUtils.getEChartsInstance();
                
                if (!chartInstance) {
                    console.log('第一次获取ECharts实例失败，3秒后重试...');
                    setTimeout(function() {
                        const retryChart = ChartUtils.getEChartsInstance();
                        if (retryChart) {
                            console.log('重试成功，初始化图表交互');
                            ChartManager.initializeChartInteractions(retryChart);
                        } else {
                            console.log('第二次重试失败，8秒后最后一次尝试...');
                            setTimeout(function() {
                                const finalRetryChart = ChartUtils.getEChartsInstance();
                                if (finalRetryChart) {
                                    console.log('最终重试成功，初始化图表交互');
                                    ChartManager.initializeChartInteractions(finalRetryChart);
                                } else {
                                    console.error('无法获取ECharts实例，请检查：');
                                    console.error('1. ECharts库是否正确加载');
                                    console.error('2. 图表HTML是否正确生成');
                                    console.error('3. 网络连接是否正常');
                                    console.error('4. pyecharts版本兼容性');
                                    
                                    // 提供手动重试选项
                                    console.log('您可以在控制台执行以下命令手动重试：');
                                    console.log('ChartManager.initializeChartInteractions(ChartUtils.getEChartsInstance())');
                                }
                            }, 8000);
                        }
                    }, 3000);
                    return;
                }
                
                console.log('成功获取ECharts实例，初始化图表交互');
                ChartManager.initializeChartInteractions(chartInstance);
            }, 2500); // 增加到2.5秒
        });
    }
}

// 导出到全局作用域（兼容现有代码）
window.ChartUtils = ChartUtils;
window.MarkPointGenerator = MarkPointGenerator;
window.EventHandler = EventHandler;
window.ChartManager = ChartManager;
window.generateMarkPointData = MarkPointGenerator.generateMarkPointData;
window.updateChartMarkPoints = ChartManager.updateChartMarkPoints;
window.getEChartsInstance = ChartUtils.getEChartsInstance;
window.initializeChartInteractions = ChartManager.initializeChartInteractions;

// 自动初始化应用
App.init();